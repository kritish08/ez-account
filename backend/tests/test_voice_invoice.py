"""Voice-created invoices must post the same books as the REST path.

The voice assistant writes to the ledger with no UI confirmation step, so
a missing entry here is invisible until someone reconciles by hand.
"""

import pytest

from services.function_executor import FunctionExecutor
from services.voice_session import VoiceSession


async def _executor(db, user_id="voice-tester"):
    return FunctionExecutor(db, VoiceSession(user_id=user_id))


async def _trial_balance(http_client, auth_headers):
    resp = await http_client.get("/api/reports/trial-balance", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _account_balance(db, account):
    rows = await db.ledger.find({"account": account}).to_list(None)
    return round(sum(r["debit"] for r in rows) - sum(r["credit"] for r in rows), 2)


@pytest.mark.asyncio
async def test_voice_invoice_with_cash_records_the_receipt(
    http_client, auth_headers, db
):
    """"Rs.5000 invoice, cash received" must put Rs.5000 into the cash account.

    Regression: save_invoice wrote `payment_received` straight onto the
    invoice's paid_amount and posted only the customer-AR debit and the
    sales credit. No cash debit, no customer credit, no payments document.
    The invoice read as paid while the cash never entered the books and
    the customer's outstanding stayed at the full amount forever.
    """
    customer = await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Sharma Ji"}
    )
    assert customer.status_code == 200, customer.text
    customer_id = customer.json()["id"]

    ex = await _executor(db)
    started = await ex.start_invoice_draft(customer_name="Sharma Ji")
    assert started.get("success") is True, started

    added = await ex.add_invoice_item(
        description="Cement Bag", quantity=1, rate=5000
    )
    assert added.get("success") is True, added

    saved = await ex.save_invoice(payment_received=5000)
    assert saved.get("success") is True, saved

    # The cash actually arrived.
    assert await _account_balance(db, "cash") == pytest.approx(5000.0)
    # And the customer does not still owe for it.
    assert await _account_balance(db, f"customer:{customer_id}") == pytest.approx(0.0)

    body = await _trial_balance(http_client, auth_headers)
    assert body["is_balanced"] is True, (
        f"debit {body['total_debit']} vs credit {body['total_credit']}"
    )


@pytest.mark.asyncio
async def test_voice_invoice_creates_a_payment_record(http_client, auth_headers, db):
    """The receipt must be a real payment document, not just a field."""
    await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Sharma Ji"}
    )

    ex = await _executor(db)
    await ex.start_invoice_draft(customer_name="Sharma Ji")
    await ex.add_invoice_item(description="Cement Bag", quantity=1, rate=5000)
    saved = await ex.save_invoice(payment_received=3000)
    assert saved.get("success") is True, saved

    payments = await db.payments.find({}).to_list(None)
    assert len(payments) == 1
    assert payments[0]["amount"] == pytest.approx(3000.0)

    invoice = await db.invoices.find_one({})
    assert invoice["paid_amount"] == pytest.approx(3000.0)
    assert invoice["status"] == "partially_paid"


@pytest.mark.asyncio
async def test_voice_invoice_without_payment_leaves_books_balanced(
    http_client, auth_headers, db
):
    """An unpaid voice invoice must not invent a cash receipt."""
    await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Sharma Ji"}
    )

    ex = await _executor(db)
    await ex.start_invoice_draft(customer_name="Sharma Ji")
    await ex.add_invoice_item(description="Cement Bag", quantity=1, rate=5000)
    saved = await ex.save_invoice(payment_received=0)
    assert saved.get("success") is True, saved

    assert await _account_balance(db, "cash") == pytest.approx(0.0)
    assert await db.payments.count_documents({}) == 0

    body = await _trial_balance(http_client, auth_headers)
    assert body["is_balanced"] is True
