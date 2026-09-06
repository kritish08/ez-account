"""Invoice / receipt image parsing via the OpenAI Responses API.

Talks to OpenAI directly (api.openai.com). This previously used Azure
OpenAI with a deployment name; the two clients also disagreed about the
endpoint format — this module stripped `/openai/...` and used
`AzureOpenAI`, while the voice handler passed the raw endpoint as a
plain `base_url`, so a single env var could not satisfy both and one of
the two features was always misconfigured. Both now use the same
native client and the same `OPENAI_API_KEY`.
"""

import base64
import json
import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

# Logger
logger = logging.getLogger(__name__)

# Vision-capable model used to read the bill. Override per-deployment.
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.6"

# Lazily-built async client — the API key may be absent in dev, and the
# rest of the app has to boot regardless.
client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI | None:
    global client
    if client:
        return client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — AI invoice parsing is unavailable.")
        return None

    # `base_url` is only for OpenAI-compatible gateways/proxies; unset means
    # api.openai.com, which is what a normal deployment wants.
    base_url = os.getenv("OPENAI_BASE_URL") or None
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return client
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {e}")
        return None

async def parse_invoice_image(file: UploadFile):
    """
    Parses an uploaded invoice image with the OpenAI Responses API.
    Returns extracted JSON data.
    """
    # 1. Save the image locally for persistence
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(upload_dir, unique_filename)

    # Hard cap on upload size. 10 MB is plenty for an invoice scan; without
    # this, a 500 MB POST would consume ~700 MB of memory (file → base64) and
    # fill disk before any rejection could happen.
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024

    # Reset file cursor to 0 before reading/saving
    await file.seek(0)

    try:
        # 1. Read & validate size FIRST, then write to disk
        file_content = await file.read()
        if len(file_content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum allowed: {MAX_UPLOAD_BYTES // (1024*1024)} MB"
            )
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Empty file upload")

        with open(file_path, "wb") as buffer:
            buffer.write(file_content)

        # URL to be stored in DB (relative path or full URL depending on how we serve statics)
        attachment_url = f"/api/uploads/{unique_filename}"

        # 2. Reuse the bytes we already read for base64 encoding
        encoded_image = base64.b64encode(file_content).decode('utf-8')

        system_prompt = """
        You are an AI assistant specialized in extracting data from invoices and receipts.

        CRITICAL PARSING RULES FOR INDIAN BILLS:
        - Numbers WITHOUT decimal points (e.g., 77, 100, 2000) are WHOLE NUMBERS.
        - "77" -> 77.00
        - "770" -> 770.00
        - DO NOT DIVIDE BY 100. "77" is NOT 0.77.
        - Numbers WITH explicit decimal points (e.g., 77.50) should be parsed as-is.

        CRITICAL QUANTITY VS AMOUNT RULE:
        - If a line item shows "1000 * 77 = 77000", the QUANTITY is 1000.
        - Sometimes the layout is confusing. TRUST THE VISUAL NUMBER.
        - If math implies a unit conversion (e.g. 77000 / 77 = 1000), but you see "10", LOOK CLOSER.
        - PRIORITY: Visual representation of quantity > Math inference.
        - However, if the Visual Quantity is clearly "1000" (e.g. 1000 pcs), Output 1000.

        Your task is to extract the following fields from the image provided:
        - supplier_name: The name of the vendor/supplier (who issued the bill). (String)
        - customer_name: The name of the customer (who received the bill). (String, null if not found)
        - date: The invoice date in YYYY-MM-DD format. (String)
        - total: The total amount as a FLOAT following the above rules. (Float)
        - invoice_number: The invoice number. (String)
        - items: A list of line items. Each item serves as a purchase item.
        - description: Product name or description.
        - quantity: Quantity purchased (default to 1 if not specified).
        - rate: Unit price/rate as a FLOAT following the above rules. (Float)
        - amount: Total amount for the line item. (Float)

        Return ONLY a valid JSON object.
        Detect the language automatically (English, Hindi, or Hinglish).
        
        CRITICAL MATH & LOGIC RULES:
        1. TRUST EXPLICIT INPUTS: If the image clearly shows "1000 * 77", then Quantity=1000 and Rate=77.
        2. IGNORE AMBIGUOUS TOTALS: If 1000 * 77 = 77,000, but the total is written as "770=00" or "770", YOU MUST RECORD THE AMOUNT AS 77,000.
        3. DO NOT DOWNGRADE RATE: Never change a clear integer rate (like 77) to a decimal (like 0.77) just to match a written total.
        4. Notation "770=00" usually means 770.00, BUT in this specific handwritten context, if the math implies 77,000, treat it as 77,000.
        5. PRIORITY ORDER: (Quantity * Rate) > Written Total.
        """

        ai = get_client()
        if not ai:
            raise HTTPException(status_code=500, detail="AI service not configured. Check server logs.")

        response = await ai.responses.create(
            model=VISION_MODEL,
            instructions=system_prompt,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Extract data from this invoice."},
                        {
                            "type": "input_image",
                            "image_url": f"data:{file.content_type};base64,{encoded_image}",
                        },
                    ],
                }
            ],
            max_output_tokens=4096,
            text={"format": {"type": "json_object"}},
        )

        content = response.output_text
        # The model might wrap JSON in markdown, so clean it up
        cleaned_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned_content)

        # Add the attachment URL to the response
        data['attachment_url'] = attachment_url

        return data

    except HTTPException:
        # Already-formatted HTTPException (size limit, missing client) — let it through unchanged.
        raise
    except Exception as e:
        # Log full detail server-side, return a generic message to the client.
        # The OpenAI SDK's `str(e)` can include the endpoint URL, model
        # name, and other infra details that should not leak.
        logger.exception(f"AI invoice parsing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="AI processing failed. Please try again or upload a clearer image."
        )
