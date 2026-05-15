"""Payment schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    customer_id: str
    amount: float = Field(..., gt=0)
    mode: str
    date: Optional[str] = None
    notes: Optional[str] = None
    use_credit: bool = False
    invoice_id: Optional[str] = None
    credit_note_id: Optional[str] = None       # CN to apply when recording payment
    advance_payment_id: Optional[str] = None   # Advance Payment to apply


class PaymentUpdate(BaseModel):
    amount: float
    mode: str
    date: Optional[str] = None
    notes: Optional[str] = None


class SupplierPaymentCreate(BaseModel):
    supplier_id: str
    amount: float = Field(..., gt=0)
    mode: str
    date: Optional[str] = None
    notes: Optional[str] = None
    purchase_id: Optional[str] = None  # optional bill-by-bill linkage
