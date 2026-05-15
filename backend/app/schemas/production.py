"""Production order schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ProductionOrderCreate(BaseModel):
    product_id: str
    # An order for 0 or negative units would still hit BOM ingredient sizing
    # (qty_required = bom_qty * order_qty) and create a meaningless work
    # order. Reject at the API boundary.
    quantity: float = Field(..., gt=0)
    batch_id: Optional[str] = None
    notes: Optional[str] = None
    planned_start_date: Optional[str] = None


class ProductionOrderUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    batch_id: Optional[str] = None
    ingredient_overrides: Optional[List[dict]] = None  # [{material_id, batch_id}]
