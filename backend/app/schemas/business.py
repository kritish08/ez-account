"""Business-setup schema."""

from typing import Optional
from pydantic import BaseModel, Field


class BusinessSetup(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    # Opening cash/bank must be non-negative — these post `cash` and `bank`
    # debit + offsetting `capital` credit ledger entries at first save. A
    # negative would invert the sign and corrupt every downstream balance.
    opening_cash: float = Field(default=0, ge=0)
    opening_bank: float = Field(default=0, ge=0)
