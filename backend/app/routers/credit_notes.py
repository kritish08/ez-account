"""Credit Notes (Sales Returns).

Creating a CN:
- Items go back into stock (inbound stock movement)
- Customer ledger gets credited (their outstanding drops)
- Sales-returns account is debited (revenue offset)

Application onto an invoice happens through
`services.payments_apply.apply_credit_note_to_invoice` from the payment
flow — this router only handles the CN doc lifecycle.

Delete reverses both the doc's own ledger / stock effects AND any
`credit_note_application` entries posted when this CN had previously
been applied to an invoice.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.credit_note import CreditNoteCreate, CreditNoteUpdate
from app.services.counters import get_next_credit_note_number
from app.services.ledger import create_ledger_entry, delete_ledger_entries
from app.services.money import _money
from app.services.stock import create_stock_movement, delete_stock_movements

router = APIRouter(prefix="/api", tags=["credit-notes"])


@router.post("/credit-notes")
async def create_credit_note(cn: CreditNoteCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": cn.customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    cn_id = str(uuid.uuid4())
    cn_number = await get_next_credit_note_number()
    cn_date = cn.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Batch-fetch product names for all line items in one query (was one
    # find_one per line).
    line_product_ids = list({i.product_id for i in cn.items if i.product_id})
    product_name_map: dict[str, str] = {}
    if line_product_ids:
        async for p in db.products.find(
            {"id": {"$in": line_product_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            product_name_map[p["id"]] = p["name"]

    items = []
    total = 0
    for item in cn.items:
        product_name = product_name_map.get(item.product_id, item.description) if item.product_id else item.description
        if item.product_id:
            # Return stock (stock in)
            await create_stock_movement(item.product_id, item.quantity, 0, "credit_note", cn_id, cn_date)

        amount = _money(item.quantity * item.rate)
        items.append({
            "product_id": item.product_id,
            "description": product_name,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        })
        total += amount

    cn_doc = {
        "id": cn_id,
        "credit_note_number": cn_number,
        "customer_id": cn.customer_id,
        "customer_name": customer["name"],
        "invoice_id": cn.invoice_id,
        "items": items,
        "total": total,
        "reason": cn.reason,
        "date": cn_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.credit_notes.insert_one(cn_doc)

    # Customer-AR credit (reduces outstanding) + sales_returns debit
    # (reduces revenue). Independent accounts — gather.
    await asyncio.gather(
        create_ledger_entry(
            f"customer:{cn.customer_id}", 0, total,
            f"Credit Note {cn_number}", "credit_note", cn_id, cn_date,
        ),
        create_ledger_entry(
            "sales_returns", total, 0,
            f"Credit Note {cn_number}", "credit_note", cn_id, cn_date,
        ),
    )

    return {"message": "Credit Note created", "id": cn_id, "credit_note_number": cn_number}


@router.put("/credit-notes/{cn_id}")
async def update_credit_note(cn_id: str, cn_update: CreditNoteUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.credit_notes.find_one({"id": cn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Credit Note not found")

    # Reverse existing effects — independent collections.
    await asyncio.gather(
        delete_stock_movements("credit_note", cn_id),
        delete_ledger_entries("credit_note", cn_id),
    )

    cn_date = cn_update.date or existing["date"]

    line_product_ids = list({i.product_id for i in cn_update.items if i.product_id})
    product_name_map: dict[str, str] = {}
    if line_product_ids:
        async for p in db.products.find(
            {"id": {"$in": line_product_ids}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            product_name_map[p["id"]] = p["name"]

    items = []
    total = 0
    for item in cn_update.items:
        product_name = product_name_map.get(item.product_id, item.description) if item.product_id else item.description
        if item.product_id:
            # Return stock (stock in)
            await create_stock_movement(item.product_id, item.quantity, 0, "credit_note", cn_id, cn_date)

        amount = _money(item.quantity * item.rate)
        items.append({
            "product_id": item.product_id,
            "description": product_name,
            "quantity": item.quantity,
            "rate": item.rate,
            "amount": amount
        })
        total += amount

    update_data = {
        "items": items,
        "total": total,
        "reason": cn_update.reason,
        "date": cn_date,
        "invoice_id": cn_update.invoice_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.credit_notes.update_one({"id": cn_id}, {"$set": update_data})

    # Re-create both ledger sides (fixes missing sales_returns on update).
    # Independent accounts — gather.
    await asyncio.gather(
        create_ledger_entry(
            f"customer:{existing['customer_id']}", 0, total,
            f"Credit Note {existing['credit_note_number']}", "credit_note", cn_id, cn_date,
        ),
        create_ledger_entry(
            "sales_returns", total, 0,
            f"Credit Note {existing['credit_note_number']}", "credit_note", cn_id, cn_date,
        ),
    )

    return {"message": "Credit Note updated"}


@router.get("/credit-notes")
async def list_credit_notes(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    notes = await db.credit_notes.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return notes


@router.get("/credit-notes/{cn_id}")
async def get_credit_note(cn_id: str, current_user: dict = Depends(get_current_user)):
    cn = await db.credit_notes.find_one({"id": cn_id}, {"_id": 0})
    if not cn:
        raise HTTPException(status_code=404, detail="Credit Note not found")
    return cn


@router.delete("/credit-notes/{cn_id}")
async def delete_credit_note(cn_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.credit_notes.find_one({"id": cn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Credit Note not found")

    # Reverse the CN amount already applied to any linked invoice.
    # When a CN is applied via apply_credit_note_to_invoice, the invoice's
    # paid_amount is increased and the CN's total is decreased. Deleting the
    # CN must undo this.
    if existing.get("invoice_id"):
        linked_invoice = await db.invoices.find_one({"id": existing["invoice_id"]})
        if linked_invoice:
            cn_applied = linked_invoice.get("credit_note_applied", 0)
            if cn_applied > 0:
                new_paid = max(0, linked_invoice.get("paid_amount", 0) - cn_applied)
                new_status = "paid" if new_paid >= linked_invoice["total"] else ("partially_paid" if new_paid > 0 else "unpaid")
                await db.invoices.update_one(
                    {"id": existing["invoice_id"]},
                    {"$set": {"paid_amount": new_paid, "status": new_status, "credit_note_applied": 0}}
                )

    # Independent collections — gather to overlap round-trips.
    # We only reverse the on-create ledger pair (ref_type="credit_note");
    # CN application no longer posts a separate ledger entry, so there's
    # nothing under ref_type="credit_note_application" to clean up.
    await asyncio.gather(
        delete_stock_movements("credit_note", cn_id),
        delete_ledger_entries("credit_note", cn_id),
    )
    await db.credit_notes.delete_one({"id": cn_id})

    return {"message": "Credit Note deleted and effects reversed"}
