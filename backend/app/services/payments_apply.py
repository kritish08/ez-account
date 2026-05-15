"""Money-movement helpers — payments → invoices, CN/DN application, etc.

These are the atomic, $inc-guarded helpers behind FIN-P0-1 (CN double
spend) and FIN-P0-2 (payment double-allocate). They live separately
from the routes so the same logic can be reused by REST + voice + any
future surface without duplicating subtle guards.
"""

import uuid
from datetime import datetime, timezone

from app.database import db
from app.services.ledger import create_ledger_entry, get_account_balance
from app.services.money import _money


async def apply_payment_fifo(customer_id: str, amount: float, payment_id: str):
    """Apply a payment to the customer's oldest unpaid invoices first (FIFO)."""
    remaining = amount

    invoices = await db.invoices.find(
        {"customer_id": customer_id, "status": {"$nin": ["paid", "draft"]}},
        {"_id": 0},
    ).sort("date", 1).to_list(None)

    for invoice in invoices:
        if remaining <= 0:
            break

        outstanding = invoice["total"] - invoice.get("paid_amount", 0)
        if outstanding <= 0:
            continue

        apply_amount = min(remaining, outstanding)
        new_paid = _money(invoice.get("paid_amount", 0) + apply_amount)
        new_status = "paid" if new_paid >= invoice["total"] else "partially_paid"

        await db.invoices.update_one(
            {"id": invoice["id"]},
            {"$set": {"paid_amount": new_paid, "status": new_status}},
        )

        await db.payment_allocations.insert_one({
            "id": str(uuid.uuid4()),
            "payment_id": payment_id,
            "invoice_id": invoice["id"],
            "amount": apply_amount,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        remaining -= apply_amount

    return remaining


async def get_customer_credit(customer_id: str) -> float:
    """Customer's available credit balance (sum of unconsumed credit notes)."""
    pipeline = [
        {"$match": {"customer_id": customer_id, "total": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    result = await db.credit_notes.aggregate(pipeline).to_list(1)
    if result:
        return round(result[0]["total"], 2)
    return 0.0


async def apply_debit_to_purchase(supplier_id: str, purchase_id: str, purchase_total: float) -> tuple:
    """Apply any existing Supplier Debit (Advance) to a new purchase.

    Returns `(amount_due, debit_applied)`. See the inline comments for the
    pre-balance reasoning.
    """
    current_balance = await get_account_balance(f"supplier:{supplier_id}")
    pre_balance = current_balance + purchase_total
    available_debit = max(0, pre_balance)
    debit_applied = min(available_debit, purchase_total)
    amount_due = purchase_total - debit_applied

    if amount_due <= 0:
        new_status = "paid"
    elif amount_due < purchase_total:
        new_status = "partially_paid"
    else:
        new_status = "unpaid"

    await db.purchases.update_one(
        {"id": purchase_id},
        {"$set": {
            "payment_status": new_status,
            "debit_used": debit_applied,
            "amount_due": amount_due,
        }},
    )
    return amount_due, debit_applied


async def apply_credit_to_invoice(customer_id: str, invoice_id: str, invoice_total: float) -> tuple:
    """Apply available customer-ledger credit to a new invoice.

    Returns `(amount_due, credit_applied)`.
    """
    current_balance = await get_account_balance(f"customer:{customer_id}")
    pre_balance = current_balance - invoice_total
    available_credit = max(0, -pre_balance)

    if available_credit <= 0:
        return invoice_total, 0

    allocations = await db.payment_allocations.find({"invoice_id": invoice_id}).to_list(None)
    cash_paid = sum(a["amount"] for a in allocations)
    needed_amount = max(0, invoice_total - cash_paid)
    credit_applied = min(available_credit, needed_amount)

    total_paid = cash_paid + credit_applied
    amount_due = invoice_total - total_paid
    new_status = "paid" if amount_due <= 0 else "partially_paid"

    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "paid_amount": total_paid,
            "status": new_status,
            "credit_applied": credit_applied,
        }},
    )
    return amount_due, credit_applied


async def apply_credit_note_to_invoice(credit_note_id: str, invoice_id: str) -> float:
    """Atomic credit-note application — guards against double-spend (FIN-P0-1).

    Decrements CN balance + increments invoice paid_amount using guarded
    `$inc`s. If either side races, the CN side is rolled back so books stay
    balanced. Posts the customer-ledger relief entry (CN-LEDGER fix).
    """
    cn = await db.credit_notes.find_one({"id": credit_note_id})
    if not cn or cn["total"] <= 0:
        return 0

    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        return 0

    invoice_due = round(invoice["total"] - invoice.get("paid_amount", 0), 2)
    if invoice_due <= 0:
        return 0

    apply_amount = round(min(cn["total"], invoice_due), 2)

    # Atomically decrement CN with a >= filter — no negative balances.
    cn_result = await db.credit_notes.update_one(
        {"id": credit_note_id, "total": {"$gte": apply_amount}},
        {"$inc": {"total": -apply_amount}},
    )
    if cn_result.modified_count == 0:
        return 0  # raced — another request consumed it

    # Atomically increment invoice with a ceiling filter — no over-payment.
    inv_result = await db.invoices.update_one(
        {
            "id": invoice_id,
            "paid_amount": {"$lte": round(invoice["total"] - apply_amount, 2)},
        },
        {"$inc": {"paid_amount": apply_amount, "credit_note_applied": apply_amount}},
    )
    if inv_result.modified_count == 0:
        # Roll back the CN side so books stay balanced.
        await db.credit_notes.update_one(
            {"id": credit_note_id},
            {"$inc": {"total": apply_amount}},
        )
        return 0

    # Reconcile status from the now-current paid_amount.
    updated_inv = await db.invoices.find_one(
        {"id": invoice_id},
        {"_id": 0, "total": 1, "paid_amount": 1, "customer_id": 1, "invoice_number": 1, "date": 1},
    )
    if updated_inv:
        new_status = "paid" if updated_inv["paid_amount"] >= updated_inv["total"] else "partially_paid"
        await db.invoices.update_one({"id": invoice_id}, {"$set": {"status": new_status}})

        # Customer-ledger relief: the CN itself didn't post a customer entry
        # when first created (only on application), so without this the
        # outstanding balance stays stale.
        if updated_inv.get("customer_id"):
            await create_ledger_entry(
                account=f"customer:{updated_inv['customer_id']}",
                debit=0,
                credit=apply_amount,
                narration=f"Credit Note applied to Invoice {updated_inv.get('invoice_number', invoice_id)}",
                ref_type="credit_note_application",
                ref_id=credit_note_id,
                date=updated_inv.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )

    return apply_amount


async def apply_advance_payment_to_invoice(advance_payment_id: str, invoice_id: str) -> float:
    """Apply an Advance Payment to an invoice."""
    adv = await db.advance_payments.find_one({"id": advance_payment_id})
    if not adv or adv.get("remaining_amount", 0) <= 0:
        return 0

    invoice = await db.invoices.find_one({"id": invoice_id})
    if not invoice:
        return 0

    invoice_due = invoice["total"] - invoice.get("paid_amount", 0)
    if invoice_due <= 0:
        return 0

    apply_amount = round(min(adv["remaining_amount"], invoice_due), 2)
    new_adv_remaining = round(adv["remaining_amount"] - apply_amount, 2)
    new_paid = round(invoice.get("paid_amount", 0) + apply_amount, 2)
    new_status = "paid" if new_paid >= invoice["total"] else "partially_paid"

    await db.advance_payments.update_one(
        {"id": advance_payment_id},
        {"$set": {"remaining_amount": new_adv_remaining}},
    )
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {
            "paid_amount": new_paid,
            "status": new_status,
            "advance_payment_applied": invoice.get("advance_payment_applied", 0) + apply_amount,
        }},
    )

    # Link the original payment to this invoice for rollback support.
    await db.payment_allocations.insert_one({
        "id": str(uuid.uuid4()),
        "payment_id": adv["payment_id"],
        "invoice_id": invoice_id,
        "amount": apply_amount,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # No customer-ledger entry needed — the customer was already credited
    # when the Advance Payment was first received as cash.
    return apply_amount
