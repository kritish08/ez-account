"""Purchase schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class PurchaseItem(BaseModel):
    product_id: Optional[str] = None
    # Quantity & price guards — accepting negatives or zero silently corrupts
    # stock (a negative purchase quantity credits stock instead of debiting)
    # and ledger sums. Validators reject those at the API boundary.
    quantity: float = Field(..., gt=0)
    cost_price: float = Field(..., ge=0)
    batch_id: Optional[str] = None
    serial_numbers: Optional[List[str]] = None


class PurchaseCreate(BaseModel):
    supplier_id: Optional[str] = None
    items: List[PurchaseItem]
    payment_status: str = "unpaid"  # cash, bank, unpaid
    date: Optional[str] = None
    notes: Optional[str] = None
    attachment_url: Optional[str] = None
    apply_debit: bool = False


class PurchaseUpdate(BaseModel):
    supplier_id: Optional[str] = None
    items: List[PurchaseItem]
    payment_status: str = "unpaid"
    date: Optional[str] = None
    notes: Optional[str] = None
    attachment_url: Optional[str] = None
    apply_debit: bool = False
