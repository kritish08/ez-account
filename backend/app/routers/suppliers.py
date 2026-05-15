"""Supplier CRUD + payable / ledger views.

Supplier accounts are liabilities: `credit - debit` is what we owe them.
The list endpoint is N+1-free (single ledger aggregation), and delete
guards against orphan FKs by checking every collection that references
the supplier, then sweeps the opening-balance setup entries so the
trial balance stays clean.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.supplier import SupplierCreate, SupplierUpdate
from app.services.ledger import create_ledger_entry, delete_ledger_entries, get_account_balance

router = APIRouter(prefix="/api", tags=["suppliers"])


@router.post("/suppliers")
async def create_supplier(supplier: SupplierCreate, current_user: dict = Depends(get_current_user)):
    supplier_id = str(uuid.uuid4())
    supplier_doc = {
        "id": supplier_id,
        **supplier.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.suppliers.insert_one(supplier_doc)

    # Post the two opening-balance ledger entries in parallel — they target
    # different accounts (supplier:X liability + capital equity), no
    # dependency between them.
    if supplier.opening_balance > 0:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await asyncio.gather(
            create_ledger_entry(f"supplier:{supplier_id}", 0, supplier.opening_balance, "Opening balance payable", "setup", supplier_id, today),
            # Debit Capital (Liability reduces Equity)
            create_ledger_entry("capital", supplier.opening_balance, 0, "Opening capital (supplier)", "setup", supplier_id, today),
        )

    return {"message": "Supplier created", "id": supplier_id}


@router.get("/suppliers")
async def list_suppliers(current_user: dict = Depends(get_current_user)):
    """List suppliers with payable balance. Single aggregation, no N+1."""
    # Aggregate by account-prefix `^supplier:` so the ledger query has no
    # dependency on the suppliers list (was previously $in supplier_accounts
    # which forced sequential). Orphaned-supplier ledger rows, if any, are
    # filtered out by the supplier-iteration loop below.
    pipeline = [
        {"$match": {"account": {"$regex": "^supplier:"}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    suppliers, balance_rows = await asyncio.gather(
        db.suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(None),
        db.ledger.aggregate(pipeline).to_list(None),
    )
    if not suppliers:
        return []

    balance_map = {row["_id"].split(":", 1)[1]: row["balance"] for row in balance_rows}
    for supplier in suppliers:
        # Payable = credits - debits (we owe them)
        balance = balance_map.get(supplier["id"], 0)
        supplier["payable"] = max(0, -balance)

    return suppliers


@router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, current_user: dict = Depends(get_current_user)):
    # Two reads, no dependency between them — gather, then 404.
    supplier, balance = await asyncio.gather(
        db.suppliers.find_one({"id": supplier_id}, {"_id": 0}),
        get_account_balance(f"supplier:{supplier_id}"),
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    supplier["payable"] = max(0, -balance)
    return supplier


@router.get("/suppliers/{supplier_id}/ledger")
async def get_supplier_ledger(supplier_id: str, current_user: dict = Depends(get_current_user)):
    # Fetch supplier + ledger entries in parallel — both keyed off the same
    # id, no dependency between them. 404 check runs after gather; the
    # extra ledger query is cheap and only wasted on the rare 404 path.
    supplier, entries = await asyncio.gather(
        db.suppliers.find_one({"id": supplier_id}, {"_id": 0}),
        db.ledger.find(
            {"account": f"supplier:{supplier_id}"},
            {"_id": 0},
        ).sort("date", 1).to_list(None),
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Supplier accounts are liabilities:
    #   Credit = new purchase / debit-note → increases what we owe
    #   Debit  = payment made / purchase return → decreases what we owe

    ledger = []
    running_balance = 0

    for entry in entries:
        # Supplier is Liability: Credit increases, Debit decreases
        # Balance = Credits - Debits
        running_balance += entry["credit"] - entry["debit"]

        if entry["credit"] > 0:
            description = f"Purchase - {entry['narration']}"
            amount = entry["credit"]
            type_ = "purchase"
        else:
            description = f"Payment Made - {entry['narration']}"
            amount = entry["debit"]
            type_ = "payment"

        ledger.append({
            "date": entry["date"],
            "description": description,
            "amount": amount,
            "type": type_,
            "balance": running_balance
        })

    return {"supplier": supplier, "ledger": ledger, "current_balance": running_balance}


@router.put("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, supplier: SupplierUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.suppliers.find_one({"id": supplier_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier not found")

    update_data = supplier.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.suppliers.update_one({"id": supplier_id}, {"$set": update_data})
    return {"message": "Supplier updated"}


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.suppliers.find_one({"id": supplier_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Check for ALL dependencies in parallel (each count_documents was a
    # separate round-trip; on the happy path all three are zero so they're
    # free to overlap). Previously only the purchases collection was
    # checked, so a supplier with debit notes or supplier payments would
    # be deleted with stale references left behind, plus the opening-
    # balance ledger entries.
    purchases, debit_notes, sup_payments = await asyncio.gather(
        db.purchases.count_documents({"supplier_id": supplier_id}),
        db.debit_notes.count_documents({"supplier_id": supplier_id}),
        db.supplier_payments.count_documents({"supplier_id": supplier_id}),
    )
    if purchases > 0:
        raise HTTPException(status_code=400, detail="Cannot delete supplier with existing purchases")
    if debit_notes > 0:
        raise HTTPException(status_code=400, detail="Cannot delete supplier with existing debit notes")
    if sup_payments > 0:
        raise HTTPException(status_code=400, detail="Cannot delete supplier with existing payments")

    # Clean up opening-balance ledger entries posted at supplier creation
    # (otherwise they linger forever and pollute trial balance / reports).
    await delete_ledger_entries("setup", supplier_id)

    await db.suppliers.delete_one({"id": supplier_id})
    return {"message": "Supplier deleted"}
