"""AI features — currently just invoice-image parsing.

Hand-off to `services.ai_service.parse_invoice_image` which talks to
the configured vision model. Internal exception details are swallowed
on the response so we never leak prompt/model errors to the client.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.deps import get_current_user
from services.ai_service import parse_invoice_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/ai/parse-invoice")
async def parse_invoice_endpoint(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    try:
        content_type = file.content_type
        if content_type not in ["image/jpeg", "image/png", "application/pdf"]:
            # gpt-4o handles images best. PDFs may need conversion upstream.
            # No-op here; the service decides what to do with non-image content.
            pass

        data = await parse_invoice_image(file)
        return data

    except HTTPException:
        raise
    except Exception as e:
        # Don't leak internal exception details to the client.
        logger.exception(f"AI Parse Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse invoice. Please try again.")
