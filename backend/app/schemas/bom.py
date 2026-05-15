"""Bill-of-Materials schemas."""

from typing import List, Optional
from pydantic import BaseModel


class BOMComponent(BaseModel):
    material_id: str
    quantity: float
    unit: Optional[str] = None


class BOMCreate(BaseModel):
    version: str = "1.0"
    components: List[BOMComponent]
