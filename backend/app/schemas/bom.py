"""Bill-of-Materials schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class BOMComponent(BaseModel):
    material_id: str
    # A BOM line with zero or negative quantity is nonsense — production-order
    # creation multiplies it by order quantity to size ingredient demand.
    quantity: float = Field(..., gt=0)
    unit: Optional[str] = None


class BOMCreate(BaseModel):
    version: str = "1.0"
    components: List[BOMComponent]
