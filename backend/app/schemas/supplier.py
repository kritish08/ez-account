"""Supplier schemas."""

from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.common import GSTIN


class SupplierCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: GSTIN = None
    state_code: Optional[str] = None
    opening_balance: float = Field(default=0, ge=0)


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: GSTIN = None
    state_code: Optional[str] = None
