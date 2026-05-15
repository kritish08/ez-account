"""Credit note (sales return) schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class CreditNoteItem(BaseModel):
    product_id: Optional[str] = None
    description: str
    quantity: float = Field(..., gt=0)
    rate: float = Field(..., ge=0)


class CreditNoteCreate(BaseModel):
    customer_id: str
    invoice_id: Optional[str] = None
    items: List[CreditNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None


class CreditNoteUpdate(BaseModel):
    items: List[CreditNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None
    invoice_id: Optional[str] = None
