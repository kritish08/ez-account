"""Customer schemas."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    # Opening balance must be non-negative — the direction (debit/credit) is
    # captured by `balance_type`. Allowing negative here led to ledger entries
    # with the wrong sign.
    opening_balance: float = Field(default=0, ge=0)
    # "debit" = customer owes us (AR), "credit" = customer prepaid us.
    # Anything else used to silently fall through the if/else and post the
    # opening balance as a credit (prepaid) regardless of intent.
    balance_type: Literal["debit", "credit"] = "debit"


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
