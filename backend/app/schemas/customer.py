"""Customer schemas."""

from typing import Optional
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
    balance_type: Optional[str] = "debit"  # "debit" = AR (customer owes us), "credit" = customer prepaid us


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
