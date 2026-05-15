"""Business-setup schema."""

from typing import Optional
from pydantic import BaseModel


class BusinessSetup(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    opening_cash: float = 0
    opening_bank: float = 0
