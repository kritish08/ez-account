"""Expense schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    description: str
    amount: float = Field(..., gt=0)
    mode: str
    category: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None


class ExpenseUpdate(BaseModel):
    description: str
    amount: float = Field(..., gt=0)
    mode: str
    category: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None
