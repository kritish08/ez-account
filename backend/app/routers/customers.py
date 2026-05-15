"""Customer CRUD + outstanding / credit balance + full statement.

The list endpoint was the original "customers fail to load" hotspot —
it now serves N customers in 3 queries regardless of N. The statement
endpoint stitches invoices + payments + credit-note creations +
credit-note applications + opening balance into a chronological,
running-balance ledger; sort order is timestamp-then-type-priority so
same-day rows are deterministic.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.ledger import create_ledger_entry, delete_ledger_entries, get_account_balance
from app.services.payments_apply import get_customer_credit

router = APIRouter(prefix="/api", tags=["customers"])


@router.post("/customers")
async def create_customer(customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    customer_id = str(uuid.uuid4())
    customer_doc = {
        "id": customer_id,
        **customer.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.customers.insert_one(customer_doc)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if customer.opening_balance > 0:
        if customer.balance_type == "debit":
            await create_ledger_entry(f"customer:{customer_id}", customer.opening_balance, 0, "Opening balance", "setup", customer_id, today)
            # Credit Capital (Asset increases Equity)
            await create_ledger_entry("capital", 0, customer.opening_balance, "Opening capital (customer)", "setup", customer_id, today)
        else:
            await create_ledger_entry(f"customer_credit:{customer_id}", 0, customer.opening_balance, "Opening credit balance", "setup", customer_id, today)
            # Debit Capital (Liability reduces Equity)
            await create_ledger_entry("capital", customer.opening_balance, 0, "Opening capital (customer)", "setup", customer_id, today)

    return {"message": "Customer created", "id": customer_id}


@router.get("/customers")
async def list_customers(current_user: dict = Depends(get_current_user)):
    """List customers with outstanding + available credit.

    Previously this issued 2 aggregations per customer (N+1). With N=100
    that was 200 sequential MongoDB round-trips and was the primary cause
    of "customers fail to load" timeouts. Now: 3 queries regardless of N.
    """
    customers = await db.customers.find({}, {"_id": 0}).sort("name", 1).to_list(None)
    if not customers:
        return []

    customer_ids = [c["id"] for c in customers]
    customer_accounts = [f"customer:{cid}" for cid in customer_ids]

    # Outstanding per customer in one aggregation
    outstanding_map = {}
    outstanding_pipeline = [
        {"$match": {"account": {"$in": customer_accounts}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    async for row in db.ledger.aggregate(outstanding_pipeline):
        cid = row["_id"].split(":", 1)[1]
        outstanding_map[cid] = round(row["balance"], 2)

    # Available credit per customer in one aggregation
    credit_map = {}
    credit_pipeline = [
        {"$match": {"customer_id": {"$in": customer_ids}, "total": {"$gt": 0}}},
        {"$group": {"_id": "$customer_id", "credit": {"$sum": "$total"}}},
    ]
    async for row in db.credit_notes.aggregate(credit_pipeline):
        credit_map[row["_id"]] = round(row["credit"], 2)

    for customer in customers:
        customer["outstanding"] = outstanding_map.get(customer["id"], 0.0)
        customer["credit"] = credit_map.get(customer["id"], 0.0)

    return customers


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer["outstanding"] = await get_account_balance(f"customer:{customer_id}")
    customer["credit"] = await get_customer_credit(customer_id)
    return customer


@router.put("/customers/{customer_id}")
async def update_customer(customer_id: str, customer: CustomerUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.customers.find_one({"id": customer_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Use CustomerUpdate (all optional) instead of CustomerCreate to match
    # what an update actually accepts. Opening-balance / balance-type are
    # intentionally NOT updatable here — changing them would invalidate
    # historic ledger entries; users must adjust via a manual journal.
    update_data = customer.model_dump(exclude_unset=True)
    update_data.pop("opening_balance", None)
    update_data.pop("balance_type", None)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.customers.update_one({"id": customer_id}, {"$set": update_data})
    return {"message": "Customer updated"}


@router.get("/customers/{customer_id}/ledger")
async def get_customer_ledger(
    customer_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    customer = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Build the date-range filters once and reuse across the four
    # collection-level queries.
    def _date_filter(base: dict) -> dict:
        q = dict(base)
        if start_date:
            q.setdefault("date", {})["$gte"] = start_date
        if end_date:
            q.setdefault("date", {})["$lte"] = end_date
        return q

    inv_query = _date_filter({"customer_id": customer_id})
    pay_query = _date_filter({"customer_id": customer_id})
    cn_query = _date_filter({"customer_id": customer_id})
    cn_app_query = _date_filter({"account": f"customer:{customer_id}", "ref_type": "credit_note_application"})

    # Applied-credit map is keyed by ref_id (= payment_id) and filtered by
    # the customer-account narration — independent of the payments query
    # itself, so it can be gathered in parallel.
    async def _applied_credit_map() -> dict:
        m: dict[str, float] = {}
        async for entry in db.ledger.find(
            {
                "ref_type": "payment",
                "account": f"customer:{customer_id}",
                "narration": "Payment applied to invoices",
            },
            {"_id": 0, "ref_id": 1, "credit": 1},
        ):
            m[entry["ref_id"]] = entry.get("credit", 0)
        return m

    # All 8 reads below are independent — fire them in one parallel batch.
    (
        invoices,
        payments,
        credit_notes,
        cn_applications,
        opening_bals,
        applied_credit_map,
        cn_balance,
        advance_payments,
    ) = await asyncio.gather(
        db.invoices.find(inv_query, {"_id": 0}).to_list(None),
        db.payments.find(pay_query, {"_id": 0}).to_list(None),
        db.credit_notes.find(cn_query, {"_id": 0}).to_list(None),
        db.ledger.find(cn_app_query, {"_id": 0}).to_list(None),
        db.ledger.find(
            {"account": f"customer:{customer_id}", "ref_type": "setup"},
            {"_id": 0},
        ).to_list(10),
        _applied_credit_map(),
        get_customer_credit(customer_id),
        db.advance_payments.find(
            {"customer_id": customer_id, "remaining_amount": {"$gt": 0}},
            {"_id": 0},
        ).to_list(100),
    )

    rows = []

    # ---- Invoices (Debit) ----
    for inv in invoices:
        rows.append({
            "timestamp": inv.get("created_at", inv.get("date", "") + "T00:00:00Z"),
            "date": inv.get("date", ""),
            "type": "invoice",
            "ref_number": inv.get("invoice_number", ""),
            "ref_id": inv.get("id", ""),
            "narration": f"Invoice — {inv.get('invoice_number', '')}",
            "debit": inv.get("total", 0),
            "credit": 0,
            "status": inv.get("status", ""),
        })

    # ---- Payments (Credit) ----
    # Narration-filtered ledger map (built in the parallel batch above)
    # pins us to the applied-portion row even when a payment also has an
    # advance overflow on the same customer:X account — see iteration 7
    # for the original double-count fix.
    for pay in payments:
        applied_credit = applied_credit_map.get(pay.get("id"), 0)
        rows.append({
            "timestamp": pay.get("created_at", pay.get("date", "") + "T00:00:00Z"),
            "date": pay.get("date", ""),
            "type": "payment",
            "ref_number": "",
            "ref_id": pay.get("id", ""),
            "narration": f"Payment — {pay.get('mode', '').capitalize()}{(' · ' + pay['notes']) if pay.get('notes') else ''}",
            "debit": 0,
            "credit": applied_credit,
            "status": "",
        })

    # ---- Credit Notes created (Credit, but doesn't reduce outstanding yet) ----
    for cn in credit_notes:
        rows.append({
            "timestamp": cn.get("created_at", cn.get("date", "") + "T00:00:00Z"),
            "date": cn.get("date", ""),
            "type": "credit_note",
            "ref_number": cn.get("credit_note_number", ""),
            "ref_id": cn.get("id", ""),
            "narration": f"Credit Note {cn.get('credit_note_number', '')} — {cn.get('reason', '')}",
            "debit": 0,
            "credit": 0,  # CN Creation DOES NOT reduce outstanding
            "cn_total": cn.get("total", 0),
            "status": "active" if cn.get("total", 0) > 0 else "exhausted",
        })

    # ---- Credit Note Applications (Credit - reduces outstanding) ----
    for cn_app in cn_applications:
        # ledger entries lack created_at; pin them to end-of-day so they sort
        # after the invoice they apply to.
        rows.append({
            "timestamp": cn_app.get("date", "") + "T23:59:59Z",
            "date": cn_app.get("date", ""),
            "type": "credit_note_application",
            "ref_number": "",
            "ref_id": cn_app.get("ref_id", ""),
            "narration": cn_app.get("narration", "Credit Note Applied"),
            "debit": 0,
            "credit": cn_app.get("credit", 0),
            "status": "",
        })

    # ---- Opening Balance ----
    for ob in opening_bals:
        rows.append({
            "timestamp": ob.get("date", "") + "T00:00:00Z",
            "date": ob.get("date", ""),
            "type": "opening_balance",
            "ref_number": "",
            "ref_id": ob.get("ref_id", ""),
            "narration": "Opening Balance",
            "debit": ob.get("debit", 0),
            "credit": ob.get("credit", 0),
            "status": "",
        })

    # Sort all rows strictly by exact timestamp, then by type priority if timestamps match
    type_priority = {"opening_balance": 0, "invoice": 1, "payment": 2, "credit_note": 3, "credit_note_application": 4}
    rows.sort(key=lambda r: (r.get("timestamp", ""), type_priority.get(r["type"], 99)))

    # Compute running balance chronologically
    running_balance = 0
    ledger = []

    total_invoiced = 0
    total_paid = 0

    for row in rows:
        running_balance += row["debit"] - row["credit"]
        entry = {**row, "balance": round(running_balance, 2)}
        ledger.append(entry)

        if row["type"] == "invoice":
            total_invoiced += row["debit"]
        elif row["type"] == "payment" or row["type"] == "credit_note_application":
            total_paid += row["credit"]

    # For opening balance, if debit, it acts like invoiced, if credit, acts like paid
    for ob in opening_bals:
        total_invoiced += ob.get("debit", 0)
        total_paid += ob.get("credit", 0)

    adv_balance = sum([a["remaining_amount"] for a in advance_payments])

    return {
        "customer": {
            **customer,
            "outstanding": round(running_balance, 2),
            "credit": cn_balance,
            "advance_balance": adv_balance
        },
        "ledger": ledger,
        "summary": {
            "total_invoiced": round(total_invoiced, 2),
            "total_paid": round(total_paid, 2),
            "outstanding": round(running_balance, 2),
            "cn_balance": cn_balance,
            "adv_balance": round(adv_balance, 2)
        },
        "credit_notes": credit_notes,
        "advance_payments": advance_payments
    }


@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.customers.find_one({"id": customer_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check ALL dependencies in parallel — on the happy path all four are
    # zero so they overlap nicely. Previously a customer with only credit-
    # notes or advance-payments could be deleted while leaving orphaned
    # references.
    invoices, payments, credit_notes, advance_payments = await asyncio.gather(
        db.invoices.count_documents({"customer_id": customer_id}),
        db.payments.count_documents({"customer_id": customer_id}),
        db.credit_notes.count_documents({"customer_id": customer_id}),
        db.advance_payments.count_documents({"customer_id": customer_id}),
    )
    if invoices > 0:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing invoices")
    if payments > 0:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing payments")
    if credit_notes > 0:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing credit notes")
    if advance_payments > 0:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing advance payments")

    # Clean up opening-balance ledger entries posted at customer creation.
    # Without this they'd linger forever and pollute trial balance / reports.
    await delete_ledger_entries("setup", customer_id)

    await db.customers.delete_one({"id": customer_id})
    return {"message": "Customer deleted"}
