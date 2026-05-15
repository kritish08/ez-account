"""Production order schemas."""

from typing import List, Optional
from pydantic import BaseModel


class ProductionOrderCreate(BaseModel):
    product_id: str
    quantity: float
    batch_id: Optional[str] = None
    notes: Optional[str] = None
    planned_start_date: Optional[str] = None


class ProductionOrderUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    batch_id: Optional[str] = None
    ingredient_overrides: Optional[List[dict]] = None  # [{material_id, batch_id}]
