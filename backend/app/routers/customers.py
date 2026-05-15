"""Customer CRUD + outstanding / credit balance + full statement.

The list endpoint was the original "customers fail to load" hotspot —
it now serves N customers in 3 queries regardless of N. The statement
endpoint stitches invoices + payments + credit-note creations +
credit-note applications + opening balance into a chronological,
running-balance ledger; sort order is timestamp-then-type-priority so
same-day rows are deterministic.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.ledger import create_ledger_entry, get_account_balance
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

    rows = []

    # ---- Invoices (Debit) ----
    inv_query = {"customer_id": customer_id}
    if start_date:
        inv_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        inv_query.setdefault("date", {})["$lte"] = end_date

    invoices = await db.invoices.find(inv_query, {"_id": 0}).to_list(None)
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
    pay_query = {"customer_id": customer_id}
    if start_date:
        pay_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        pay_query.setdefault("date", {})["$lte"] = end_date

    payments = await db.payments.find(pay_query, {"_id": 0}).to_list(None)
    for pay in payments:
        # To avoid double counting, we only want the payment amount applied to invoices
        # as a credit against the customer's outstanding balance.
        # Read the actual ledger entries for this payment to get the applied amount.
        pay_ledger = await db.ledger.find_one({
            "ref_type": "payment",
            "ref_id": pay.get("id"),
            "account": f"customer:{customer_id}"
        })

        applied_credit = pay_ledger["credit"] if pay_ledger else 0

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
    cn_query = {"customer_id": customer_id}
    if start_date:
        cn_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        cn_query.setdefault("date", {})["$lte"] = end_date

    credit_notes = await db.credit_notes.find(cn_query, {"_id": 0}).to_list(None)
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
            "cn_original_total": cn.get("total", 0),
            "status": "active" if cn.get("total", 0) > 0 else "exhausted",
        })

    # ---- Credit Note Applications (Credit - reduces outstanding) ----
    cn_app_query = {
        "account": f"customer:{customer_id}",
        "ref_type": "credit_note_application"
    }
    if start_date:
        cn_app_query.setdefault("date", {})["$gte"] = start_date
    if end_date:
        cn_app_query.setdefault("date", {})["$lte"] = end_date

    cn_applications = await db.ledger.find(cn_app_query, {"_id": 0}).to_list(None)
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
    opening_bal_query = {
        "account": f"customer:{customer_id}",
        "ref_type": "setup"
    }
    opening_bals = await db.ledger.find(opening_bal_query, {"_id": 0}).to_list(10)
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

    cn_balance = await get_customer_credit(customer_id)

    # Compute advance balance
    adv_cursor = db.advance_payments.find({"customer_id": customer_id, "remaining_amount": {"$gt": 0}})
    advance_payments = await adv_cursor.to_list(100)
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

    # Check dependencies
    invoices = await db.invoices.count_documents({"customer_id": customer_id})
    if invoices > 0:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing invoices")

    payments = await db.payments.count_documents({"customer_id": customer_id})
    if payments > 0:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing payments")

    await db.customers.delete_one({"id": customer_id})
    return {"message": "Customer deleted"}
