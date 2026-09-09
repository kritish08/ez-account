"""Auth + token-related shared schemas."""

from typing import Annotated, Optional
from pydantic import BaseModel, BeforeValidator, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ---- GST ----
# The GSTIN field previously accepted any string, so "hello" was storable
# and would then be printed on an invoice as if it were a tax number. This
# validates the structure and normalises case/whitespace in one place, so
# business, customer and supplier can't drift apart.
def _validate_gstin(v):
    if v is None:
        return None
    from app.services.gst import is_valid_gstin, normalize_gstin  # noqa: PLC0415

    normalized = normalize_gstin(v)
    if normalized is None:
        return None
    if not is_valid_gstin(normalized):
        raise ValueError(
            "Not a valid GSTIN. Expected 15 characters: a state code, a PAN, "
            "and three trailing characters — e.g. 06AABCU9603R1ZM."
        )
    return normalized


GSTIN = Annotated[Optional[str], BeforeValidator(_validate_gstin)]
