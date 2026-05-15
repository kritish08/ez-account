"""Expense CRUD.

Every expense posts a balanced pair: credit cash/bank (the money leaves)
and debit `expense:{category}` (the expense category accumulates).
Edit reverses the previous ledger pair and re-posts a fresh one with the
new amount/category/mode so the trial balance always reconciles.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services.ledger import create_ledger_entry, delete_ledger_entries

router = APIRouter(prefix="/api", tags=["expenses"])


@router.post("/expenses")
async def create_expense(expense: ExpenseCreate, current_user: dict = Depends(get_current_user)):
    expense_id = str(uuid.uuid4())
    expense_date = expense.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    expense_doc = {
        "id": expense_id,
        **expense.model_dump(),
        "date": expense_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.expenses.insert_one(expense_doc)

    # Cash/bank credit (money out) + expense-category debit — independent
    # accounts, gather.
    await asyncio.gather(
        create_ledger_entry(
            account=expense.mode,
            debit=0,
            credit=expense.amount,
            narration=f"Expense: {expense.description}",
            ref_type="expense",
            ref_id=expense_id,
            date=expense_date,
        ),
        create_ledger_entry(
            account=f"expense:{expense.category}",
            debit=expense.amount,
            credit=0,
            narration=f"Expense: {expense.description}",
            ref_type="expense",
            ref_id=expense_id,
            date=expense_date,
        ),
    )

    return {"message": "Expense recorded", "id": expense_id}


@router.get("/expenses")
async def list_expenses(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return expenses


@router.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, expense: ExpenseUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.expenses.find_one({"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Reverse Ledger
    await delete_ledger_entries("expense", expense_id)

    # Update Doc
    update_data = expense.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.expenses.update_one({"id": expense_id}, {"$set": update_data})

    # Re-create the cash-out + expense-category ledger pair in parallel.
    expense_date = expense.date or existing["date"]
    await asyncio.gather(
        create_ledger_entry(
            account=expense.mode,
            debit=0,
            credit=expense.amount,
            narration=f"Expense: {expense.description} (updated)",
            ref_type="expense",
            ref_id=expense_id,
            date=expense_date,
        ),
        create_ledger_entry(
            account=f"expense:{expense.category}",
            debit=expense.amount,
            credit=0,
            narration=f"Expense: {expense.description} (updated)",
            ref_type="expense",
            ref_id=expense_id,
            date=expense_date,
        ),
    )

    return {"message": "Expense updated"}


@router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.expenses.find_one({"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")

    await delete_ledger_entries("expense", expense_id)
    await db.expenses.delete_one({"id": expense_id})
    return {"message": "Expense deleted"}
