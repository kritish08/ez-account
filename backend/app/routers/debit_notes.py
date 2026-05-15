"""Debit Notes (Purchase Returns).

Creating a DN:
- Items leave stock (outbound stock movement)
- Supplier ledger gets debited (their payable drops)
- Purchases-returns account is credited (expense offset)

Update re-creates BOTH ledger entries (supplier debit + purchases-returns
credit). The previous version only re-posted the supplier debit, losing
the offsetting purchases-returns entry on each edit and overstating
purchase expenses.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.debit_note import DebitNoteCreate, DebitNoteUpdate
from app.services.counters import get_next_debit_note_number
from app.services.ledger import create_ledger_entry, delete_ledger_entries
from app.services.money import _money
from app.services.stock import create_stock_movement, delete_stock_movements

router = APIRouter(prefix="/api", tags=["debit-notes"])


@router.post("/debit-notes")
async def create_debit_note(dn: DebitNoteCreate, current_user: dict = Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": dn.supplier_id})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    dn_id = str(uuid.uuid4())
    dn_number = await get_next_debit_note_number()
    dn_date = dn.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    items = []
    total = 0
    for item in dn.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")

        amount = _money(item.quantity * item.cost_price)
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "amount": amount
        })
        total += amount

        # Return stock to supplier (stock out)
        await create_stock_movement(item.product_id, 0, item.quantity, "debit_note", dn_id, dn_date)

    dn_doc = {
        "id": dn_id,
        "debit_note_number": dn_number,
        "supplier_id": dn.supplier_id,
        "supplier_name": supplier["name"],
        "purchase_id": dn.purchase_id,
        "items": items,
        "total": total,
        "reason": dn.reason,
        "date": dn_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.debit_notes.insert_one(dn_doc)

    # Reduce supplier payable (debit the supplier account)
    await create_ledger_entry(
        f"supplier:{dn.supplier_id}", total, 0,
        f"Debit Note {dn_number}", "debit_note", dn_id, dn_date
    )

    # Credit Purchases Returns (reduce expense)
    await create_ledger_entry(
        "purchases_returns", 0, total,
        f"Debit Note {dn_number}", "debit_note", dn_id, dn_date
    )

    return {"message": "Debit Note created", "id": dn_id, "debit_note_number": dn_number}


@router.put("/debit-notes/{dn_id}")
async def update_debit_note(dn_id: str, dn_update: DebitNoteUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.debit_notes.find_one({"id": dn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Debit Note not found")

    # Reverse existing effects
    await delete_stock_movements("debit_note", dn_id)
    await delete_ledger_entries("debit_note", dn_id)

    dn_date = dn_update.date or existing["date"]

    items = []
    total = 0
    for item in dn_update.items:
        product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")

        amount = _money(item.quantity * item.cost_price)
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "cost_price": item.cost_price,
            "amount": amount
        })
        total += amount

        # Return stock to supplier (stock out)
        await create_stock_movement(item.product_id, 0, item.quantity, "debit_note", dn_id, dn_date)

    update_data = {
        "items": items,
        "total": total,
        "reason": dn_update.reason,
        "date": dn_date,
        "purchase_id": dn_update.purchase_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.debit_notes.update_one({"id": dn_id}, {"$set": update_data})

    # Re-create BOTH ledger entries to match create_debit_note. The previous
    # update only re-posted the supplier debit; the offsetting purchases_returns
    # credit was permanently lost on the first edit, overstating purchase expenses.
    await create_ledger_entry(
        f"supplier:{existing['supplier_id']}", total, 0,
        f"Debit Note {existing['debit_note_number']}", "debit_note", dn_id, dn_date
    )
    await create_ledger_entry(
        "purchases_returns", 0, total,
        f"Debit Note {existing['debit_note_number']}", "debit_note", dn_id, dn_date
    )

    return {"message": "Debit Note updated"}


@router.get("/debit-notes")
async def list_debit_notes(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    notes = await db.debit_notes.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return notes


@router.get("/debit-notes/{dn_id}")
async def get_debit_note(dn_id: str, current_user: dict = Depends(get_current_user)):
    dn = await db.debit_notes.find_one({"id": dn_id}, {"_id": 0})
    if not dn:
        raise HTTPException(status_code=404, detail="Debit Note not found")
    return dn


@router.delete("/debit-notes/{dn_id}")
async def delete_debit_note(dn_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.debit_notes.find_one({"id": dn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Debit Note not found")

    await delete_stock_movements("debit_note", dn_id)
    await delete_ledger_entries("debit_note", dn_id)
    await db.debit_notes.delete_one({"id": dn_id})

    return {"message": "Debit Note deleted and effects reversed"}
