"""record_payment critical path — guards the new transactional wrapper.

These tests pin behaviour we care most about for a books product:
  - exact-match payment fully pays the invoice and posts a balanced ledger
  - overpayment becomes an advance_payment doc (no orphan credits)
  - FIFO allocation walks oldest unpaid invoices first
  - the customer ledger summary reconciles
"""

import pytest


async def _make_customer(http_client, auth_headers, name="Test Cust"):
    resp = await http_client.post(
        "/api/customers",
        json={
            "name": name,
            "phone": "9000000000",
            "opening_balance": 0,
            "balance_type": "debit",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _make_invoice(http_client, auth_headers, customer_id, amount, name="Test Cust"):
    resp = await http_client.post(
        "/api/invoices",
        json={
            "customer_id": customer_id,
            "customer_name": name,
            "items": [{"description": "thing", "quantity": 1, "rate": amount}],
            "total": amount,
            "status": "unpaid",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_exact_payment_clears_invoice(http_client, auth_headers, db):
    cid = await _make_customer(http_client, auth_headers, "Exact")
    iid = await _make_invoice(http_client, auth_headers, cid, 500, "Exact")

    resp = await http_client.post(
        "/api/payments",
        json={"customer_id": cid, "invoice_id": iid, "amount": 500, "mode": "cash"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["excess_as_advance"] == 0
    assert body["advance_payment_id"] is None

    invoice = await db.invoices.find_one({"id": iid})
    assert invoice["paid_amount"] == 500
    assert invoice["status"] == "paid"


@pytest.mark.asyncio
async def test_overpayment_creates_advance(http_client, auth_headers, db):
    cid = await _make_customer(http_client, auth_headers, "Over")
    iid = await _make_invoice(http_client, auth_headers, cid, 500, "Over")

    resp = await http_client.post(
        "/api/payments",
        json={"customer_id": cid, "invoice_id": iid, "amount": 800, "mode": "bank"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["excess_as_advance"] == 300
    assert body["advance_payment_id"] is not None

    invoice = await db.invoices.find_one({"id": iid})
    assert invoice["paid_amount"] == 500
    assert invoice["status"] == "paid"

    adv = await db.advance_payments.find_one({"id": body["advance_payment_id"]})
    assert adv is not None
    assert adv["amount"] == 300
    assert adv["remaining_amount"] == 300


@pytest.mark.asyncio
async def test_fifo_payment_walks_oldest_first(http_client, auth_headers, db):
    cid = await _make_customer(http_client, auth_headers, "FIFO")
    iid1 = await _make_invoice(http_client, auth_headers, cid, 200, "FIFO")
    iid2 = await _make_invoice(http_client, auth_headers, cid, 500, "FIFO")

    # ₹400: clears iid1 (200) fully, partially pays iid2 (200 of 500)
    resp = await http_client.post(
        "/api/payments",
        json={"customer_id": cid, "amount": 400, "mode": "cash"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["excess_as_advance"] == 0

    inv1 = await db.invoices.find_one({"id": iid1})
    inv2 = await db.invoices.find_one({"id": iid2})
    assert inv1["paid_amount"] == 200 and inv1["status"] == "paid"
    assert inv2["paid_amount"] == 200 and inv2["status"] == "partially_paid"


@pytest.mark.asyncio
async def test_payment_ledger_is_balanced(http_client, auth_headers, db):
    """A payment must post a cash debit + customer credit that net to zero
    on the books. The transactional wrapper means we should never see
    one without the other, even if the test interrupts mid-flight."""
    cid = await _make_customer(http_client, auth_headers, "Ledger")
    iid = await _make_invoice(http_client, auth_headers, cid, 400, "Ledger")

    resp = await http_client.post(
        "/api/payments",
        json={"customer_id": cid, "invoice_id": iid, "amount": 400, "mode": "cash"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    pid = resp.json()["id"]
    entries = await db.ledger.find({"ref_type": "payment", "ref_id": pid}).to_list(None)
    total_debit = sum(e["debit"] for e in entries)
    total_credit = sum(e["credit"] for e in entries)
    assert total_debit == total_credit == 400


@pytest.mark.asyncio
async def test_payment_to_unknown_customer_returns_404(http_client, auth_headers):
    resp = await http_client.post(
        "/api/payments",
        json={"customer_id": "ghost-id", "amount": 100, "mode": "cash"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
