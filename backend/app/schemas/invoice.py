"""Invoice schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class InvoiceLineItem(BaseModel):
    product_id: Optional[str] = None  # None for free-text items
    description: str
    quantity: float = Field(..., gt=0)
    rate: float = Field(..., ge=0)
    batch_id: Optional[str] = None
    serial_numbers: Optional[List[str]] = None


class InvoiceCreate(BaseModel):
    customer_id: str
    items: List[InvoiceLineItem]
    notes: Optional[str] = None
    date: Optional[str] = None
    is_draft: bool = False
    attachment_url: Optional[str] = None
    apply_credit: bool = False


class InvoiceUpdate(BaseModel):
    items: List[InvoiceLineItem]
    notes: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None
    apply_credit: bool = False
