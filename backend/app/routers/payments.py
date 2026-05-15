"""Customer payments + Supplier payments.

Customer payments:
- Cash arrives → debit cash/bank, credit customer-AR
- Money is applied to invoices either targeted (single `invoice_id`) or
  FIFO across the oldest open invoices
- Any unallocated excess becomes an `advance_payment` doc (advance can be
  applied later via `apply_advance_payment_to_invoice`)
- The customer-ledger credit equals only the amount applied to invoices —
  the excess sits separately as advance, preventing double-counting

Atomic guards: the per-invoice `$inc` uses a ceiling filter
(`paid_amount <= total - apply_amt`) so two concurrent payments can't
both allocate the same outstanding balance; on race, we re-read and retry.

Supplier payments:
- Cash leaves → credit cash/bank, debit supplier (reducing payable)
- Overpayment auto-generates a debit-note as a visual marker for the
  excess. The pre-payment balance is reconstructed from the post-payment
  ledger balance (which already reflects this payment's debit entry)
  by subtracting the payment amount.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.deps import get_current_user
from app.schemas.payment import PaymentCreate, SupplierPaymentCreate
from app.services.counters import get_next_debit_note_number
from app.services.ledger import create_ledger_entry, delete_ledger_entries, get_account_balance
from app.services.payments_apply import (
    apply_advance_payment_to_invoice, apply_credit_note_to_invoice,
    apply_payment_fifo,
)

router = APIRouter(prefix="/api", tags=["payments"])


@router.post("/payments")
async def record_payment(payment: PaymentCreate, current_user: dict = Depends(get_current_user)):
    customer = await db.customers.find_one({"id": payment.customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    payment_id = str(uuid.uuid4())
    payment_date = payment.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    payment_doc = {
        "id": payment_id,
        "customer_id": payment.customer_id,
        "customer_name": customer["name"],
        "amount": payment.amount,
        "mode": payment.mode,
        "notes": payment.notes,
        "date": payment_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.payments.insert_one(payment_doc)

    await create_ledger_entry(
        account=payment.mode,
        debit=payment.amount,
        credit=0,
        narration=f"Payment from {customer['name']}",
        ref_type="payment",
        ref_id=payment_id,
        date=payment_date
    )

    excess = 0
    credit_note_applied_amount = 0

    # Step 1: Apply any existing Credit Note to the invoice FIRST (before cash payment)
    if payment.credit_note_id and payment.invoice_id:
        credit_note_applied_amount = await apply_credit_note_to_invoice(payment.credit_note_id, payment.invoice_id)

    advance_applied_amount = 0
    if payment.advance_payment_id and payment.invoice_id:
        advance_applied_amount = await apply_advance_payment_to_invoice(payment.advance_payment_id, payment.invoice_id)

    # Step 2: Determine how much cash actually needs to go to invoices
    applied_to_invoices = 0  # track actual invoice allocation for ledger entry

    if payment.invoice_id:
        invoice = await db.invoices.find_one({"id": payment.invoice_id})
        if invoice:
            outstanding = round(invoice["total"] - invoice.get("paid_amount", 0), 2)
            apply_amt = round(min(payment.amount, outstanding), 2)
            if apply_amt > 0:
                # Atomic update: $inc with a paid-ceiling filter so two
                # concurrent payments cannot both allocate the same amount.
                inv_result = await db.invoices.update_one(
                    {
                        "id": payment.invoice_id,
                        "paid_amount": {"$lte": round(invoice["total"] - apply_amt, 2)},
                    },
                    {"$inc": {"paid_amount": apply_amt}}
                )

                if inv_result.modified_count == 0:
                    # Lost the race. Re-read and recompute outstanding.
                    fresh = await db.invoices.find_one({"id": payment.invoice_id})
                    if fresh:
                        outstanding = round(fresh["total"] - fresh.get("paid_amount", 0), 2)
                        apply_amt = round(min(payment.amount, max(outstanding, 0)), 2)
                        if apply_amt > 0:
                            inv_result = await db.invoices.update_one(
                                {
                                    "id": payment.invoice_id,
                                    "paid_amount": {"$lte": round(fresh["total"] - apply_amt, 2)},
                                },
                                {"$inc": {"paid_amount": apply_amt}}
                            )

                if inv_result.modified_count > 0:
                    # Reconcile status from the now-current paid_amount.
                    updated = await db.invoices.find_one(
                        {"id": payment.invoice_id},
                        {"_id": 0, "total": 1, "paid_amount": 1},
                    )
                    if updated:
                        new_status = (
                            "paid"
                            if updated["paid_amount"] >= updated["total"]
                            else "partially_paid"
                        )
                        await db.invoices.update_one(
                            {"id": payment.invoice_id},
                            {"$set": {"status": new_status}},
                        )

                    await db.payment_allocations.insert_one({
                        "id": str(uuid.uuid4()),
                        "payment_id": payment_id,
                        "invoice_id": payment.invoice_id,
                        "amount": apply_amt,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })

                    applied_to_invoices = apply_amt
                    excess = round(payment.amount - apply_amt, 2)
                else:
                    # Invoice was concurrently fully paid by another request.
                    excess = payment.amount
            else:
                # Invoice already fully paid — full cash amount becomes excess/CN
                excess = payment.amount
        else:
            # Invoice not found — treat all as excess (Advance Payment)
            excess = payment.amount
            applied_to_invoices = 0
    else:
        # No specific invoice — apply FIFO across outstanding invoices
        excess = await apply_payment_fifo(payment.customer_id, payment.amount, payment_id)
        applied_to_invoices = payment.amount - excess

    # Credit only the amount applied to invoices to the customer ledger.
    # The excess sits separately as an advance_payment doc — keeping it out
    # of the ledger here is what prevents double-counting between the ledger
    # credit and the advance/CN balance.
    await create_ledger_entry(
        account=f"customer:{payment.customer_id}",
        debit=0,
        credit=applied_to_invoices,
        narration="Payment applied to invoices",
        ref_type="payment",
        ref_id=payment_id,
        date=payment_date
    )

    # Step 3: Create Advance Payment for overpayment instead of Credit Note
    advance_payment_id = None
    if excess > 0.009:  # avoid floating point noise
        adv_id = str(uuid.uuid4())

        adv_doc = {
            "id": adv_id,
            "customer_id": payment.customer_id,
            "customer_name": customer["name"],
            "payment_id": payment_id,
            "source_invoice_id": payment.invoice_id,
            "amount": excess,
            "remaining_amount": excess,
            "date": payment_date,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.advance_payments.insert_one(adv_doc)
        advance_payment_id = adv_id

        # Advance payments sit on the customer's ledger as credit.
        # Ref_type=payment so it rolls back with the parent payment on delete.
        await create_ledger_entry(
            account=f"customer:{payment.customer_id}",
            debit=0,
            credit=excess,
            narration=f"Advance payment received via payment ...{payment_id[-8:]}",
            ref_type="payment",
            ref_id=payment_id,
            date=payment_date
        )

    return {
        "message": "Payment recorded",
        "id": payment_id,
        "excess_as_advance": excess,
        "advance_payment_id": advance_payment_id,
        "credit_note_applied": credit_note_applied_amount,
        "advance_payment_applied": advance_applied_amount
    }


@router.get("/payments")
async def list_payments(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}

    payments = await db.payments.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return payments


@router.delete("/payments/{payment_id}")
async def delete_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.payments.find_one({"id": payment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Reverse Ledger
    await delete_ledger_entries("payment", payment_id)

    # Reverse effects on invoices (re-open them). A single payment can be
    # split across many invoices via FIFO, so pre-fetch all affected
    # invoices in one batched query instead of one find_one per allocation.
    allocations = await db.payment_allocations.find(
        {"payment_id": payment_id},
        {"_id": 0, "invoice_id": 1, "amount": 1},
    ).to_list(None)

    if allocations:
        invoice_ids = list({a["invoice_id"] for a in allocations})
        invoice_map: dict[str, dict] = {}
        async for inv in db.invoices.find(
            {"id": {"$in": invoice_ids}},
            {"_id": 0, "id": 1, "total": 1, "paid_amount": 1},
        ):
            invoice_map[inv["id"]] = inv

        # Aggregate allocations by invoice so a payment split into multiple
        # rows against the same invoice (rare but possible) is handled.
        deduct_by_invoice: dict[str, float] = {}
        for alloc in allocations:
            deduct_by_invoice[alloc["invoice_id"]] = deduct_by_invoice.get(alloc["invoice_id"], 0) + alloc["amount"]

        for invoice_id, total_deduct in deduct_by_invoice.items():
            invoice = invoice_map.get(invoice_id)
            if not invoice:
                continue
            new_paid = max(0, invoice.get("paid_amount", 0) - total_deduct)
            new_status = "partially_paid" if new_paid > 0 else "unpaid"
            if new_paid >= invoice["total"]:
                new_status = "paid"

            await db.invoices.update_one(
                {"id": invoice_id},
                {"$set": {"paid_amount": new_paid, "status": new_status}}
            )

    await db.payment_allocations.delete_many({"payment_id": payment_id})

    # Remove auto-generated credit notes and Advance Payments
    await db.credit_notes.delete_many({"payment_id": payment_id, "is_auto_generated": True})
    await db.advance_payments.delete_many({"payment_id": payment_id})

    await db.payments.delete_one({"id": payment_id})
    return {"message": "Payment voided and invoice balances reverted"}


# ============== SUPPLIER PAYMENTS ==============


@router.post("/supplier-payments")
async def record_supplier_payment(payment: SupplierPaymentCreate, current_user: dict = Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": payment.supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    payment_id = str(uuid.uuid4())
    payment_date = payment.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    payment_doc = {
        "id": payment_id,
        "supplier_id": payment.supplier_id,
        "supplier_name": supplier["name"],
        "amount": payment.amount,
        "mode": payment.mode,
        "notes": payment.notes,
        "purchase_id": payment.purchase_id,
        "date": payment_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.supplier_payments.insert_one(payment_doc)

    # Credit cash/bank
    await create_ledger_entry(
        account=payment.mode,
        debit=0,
        credit=payment.amount,
        narration=f"Payment to {supplier['name']}",
        ref_type="supplier_payment",
        ref_id=payment_id,
        date=payment_date
    )

    # Debit supplier account (reduce payable)
    await create_ledger_entry(
        account=f"supplier:{payment.supplier_id}",
        debit=payment.amount,
        credit=0,
        narration="Payment made",
        ref_type="supplier_payment",
        ref_id=payment_id,
        date=payment_date
    )

    # Check for overpayment (Debit Note). Balance is usually negative
    # (credit balance) because we owe them. Positive means we overpaid.
    balance = await get_account_balance(f"supplier:{payment.supplier_id}")

    debit_note_id = None
    if balance > 0:
        # Reconstruct the pre-payment balance: this payment posted a debit of
        # `payment.amount` to the supplier account, so subtract it from the
        # current balance to get what the balance was before this payment.
        old_balance = balance - payment.amount
        # If old_balance was -100 (we owed 100), payment 150, balance = +50, excess = 50.
        # If old_balance was +10 (they owed us 10), payment 150, balance = +160, excess = 150.

        excess = 0
        if old_balance < 0:  # We owed money
            if payment.amount > abs(old_balance):
                excess = payment.amount - abs(old_balance)
        else:  # We didn't owe, or they owed us
            excess = payment.amount

        if excess > 0:
            # Use the canonical atomic counter. The previous inline
            # find_one + increment was racy: two concurrent overpayments
            # would compute the same DN-#####, and the partial-unique
            # index on debit_note_number would 500 the slower request
            # (its payment already recorded).
            dn_number = await get_next_debit_note_number()

            dn_id = str(uuid.uuid4())
            dn_doc = {
                "id": dn_id,
                "debit_note_number": dn_number,
                "supplier_id": payment.supplier_id,
                "supplier_name": supplier["name"],
                "purchase_id": None,
                "payment_id": payment_id,
                "items": [{
                    "product_id": "OVERPAYMENT",
                    "description": "Overpayment / Advance",
                    "quantity": 1,
                    "cost_price": excess,
                }],
                "total": excess,
                "reason": f"Auto-generated from Payment {payment_id.split('-')[0]}",
                "date": payment_date,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_auto_generated": True
            }
            await db.debit_notes.insert_one(dn_doc)
            debit_note_id = dn_id

    return {"message": "Supplier payment recorded", "id": payment_id, "debit_note_id": debit_note_id}


@router.delete("/supplier-payments/{payment_id}")
async def delete_supplier_payment(payment_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.supplier_payments.find_one({"id": payment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Supplier payment not found")

    # Reverse Ledger
    await delete_ledger_entries("supplier_payment", payment_id)

    # Remove associated Advance Payments
    await db.advance_payments.delete_many({"payment_id": payment_id})

    # Remove auto-generated Debit Notes created from overpayment detection
    await db.debit_notes.delete_many({"payment_id": payment_id, "is_auto_generated": True})

    await db.supplier_payments.delete_one({"id": payment_id})
    return {"message": "Supplier payment voided and balances reverted"}
