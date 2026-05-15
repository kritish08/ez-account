"""Debit note (purchase return) schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class DebitNoteItem(BaseModel):
    product_id: str
    quantity: float = Field(..., gt=0)
    cost_price: float = Field(..., ge=0)


class DebitNoteCreate(BaseModel):
    supplier_id: str
    purchase_id: Optional[str] = None
    items: List[DebitNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None


class DebitNoteUpdate(BaseModel):
    items: List[DebitNoteItem]
    reason: Optional[str] = None
    date: Optional[str] = None
    purchase_id: Optional[str] = None
