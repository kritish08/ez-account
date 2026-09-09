"""AI features — currently just invoice-image parsing.

Hand-off to `services.ai_service.parse_invoice_image` which talks to
the configured vision model. Internal exception details are swallowed
on the response so we never leak prompt/model errors to the client.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.deps import get_current_user
from app.services.rate_limit import RateLimiter
from services.ai_service import parse_invoice_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ai"])

# Every call here runs a vision model over a 10 MB-capped upload, so an
# authenticated user could previously run up an unbounded bill. 60 scans an
# hour is far more than a shop enters by hand while capping the damage from
# a compromised account or a runaway client retry loop.
PARSE_MAX_PER_HOUR = 60
parse_limiter = RateLimiter(max_attempts=PARSE_MAX_PER_HOUR, window_seconds=60 * 60)


@router.post("/ai/parse-invoice")
async def parse_invoice_endpoint(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    quota_key = current_user.get("id") or current_user.get("email")
    retry_after = parse_limiter.retry_after(quota_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Scan limit reached ({PARSE_MAX_PER_HOUR} per hour). "
                f"Please retry in {retry_after // 60}m {retry_after % 60}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )
    # Counted before the call, so failures cost quota too — otherwise an
    # attacker gets unlimited retries by forcing errors.
    parse_limiter.record(quota_key)

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
