"""Business-setup schema."""

from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.common import GSTIN


class BusinessSetup(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: GSTIN = None
    # Place of supply for everything this business sells. Derived from the
    # GSTIN when one is given; needed explicitly for an unregistered seller.
    state_code: Optional[str] = None
    # Shops that quote MRP enter tax-inclusive prices. Treating those as
    # exclusive would overstate every invoice by the tax amount.
    price_includes_tax: bool = False
    # Opening cash/bank must be non-negative — these post `cash` and `bank`
    # debit + offsetting `capital` credit ledger entries at first save. A
    # negative would invert the sign and corrupt every downstream balance.
    opening_cash: float = Field(default=0, ge=0)
    opening_bank: float = Field(default=0, ge=0)
