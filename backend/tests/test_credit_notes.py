"""Credit-note accounting — pins the no-double-count fix.

Issuing a CN posts the journal event (debit sales_returns, credit AR).
Applying the CN to a specific invoice is an internal allocation and
must NOT post a second customer-ledger entry. Before the fix, an
applied CN of ₹X drifted the customer's outstanding balance by ₹X
because both `create_credit_note` and `apply_credit_note_to_invoice`
posted a `customer:{id}` credit.
"""

import pytest


async def _make_customer(http_client, headers, name="CN Cust"):
    resp = await http_client.post(
        "/api/customers",
        json={"name": name, "phone": "9111111111", "opening_balance": 0, "balance_type": "debit"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _make_invoice(http_client, headers, cid, amount, name="CN Cust"):
    resp = await http_client.post(
        "/api/invoices",
        json={
            "customer_id": cid,
            "customer_name": name,
            "items": [{"description": "x", "quantity": 1, "rate": amount}],
            "total": amount,
            "status": "unpaid",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _customer_balance(db, cid: str) -> float:
    """Net (debits - credits) on `customer:{cid}` — what the customer owes."""
    pipeline = [
        {"$match": {"account": f"customer:{cid}"}},
        {"$group": {"_id": None, "d": {"$sum": "$debit"}, "c": {"$sum": "$credit"}}},
    ]
    result = await db.ledger.aggregate(pipeline).to_list(1)
    if not result:
        return 0.0
    return round(result[0]["d"] - result[0]["c"], 2)


@pytest.mark.asyncio
async def test_creating_cn_credits_customer_exactly_once(http_client, auth_headers, db):
    cid = await _make_customer(http_client, auth_headers, "CN-Create")
    iid = await _make_invoice(http_client, auth_headers, cid, 1000, "CN-Create")
    # Customer owes ₹1000 after invoice
    assert await _customer_balance(db, cid) == 1000.0

    # Issue a ₹300 CN against this invoice — note: NOT yet applied
    resp = await http_client.post(
        "/api/credit-notes",
        json={
            "customer_id": cid,
            "invoice_id": iid,
            "items": [{"description": "return", "quantity": 1, "rate": 300}],
            "reason": "damaged",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    # Outstanding must drop to ₹700, NOT ₹400 (which is what double-counting produced).
    assert await _customer_balance(db, cid) == 700.0


@pytest.mark.asyncio
async def test_applying_cn_does_not_double_credit(http_client, auth_headers, db):
    """The bug: creating + applying a CN credited the customer twice."""
    cid = await _make_customer(http_client, auth_headers, "CN-Apply")
    iid = await _make_invoice(http_client, auth_headers, cid, 1000, "CN-Apply")

    # Issue a ₹300 CN
    resp = await http_client.post(
        "/api/credit-notes",
        json={
            "customer_id": cid,
            "invoice_id": iid,
            "items": [{"description": "return", "quantity": 1, "rate": 300}],
            "reason": "damaged",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    cn_id = resp.json()["id"]

    balance_before_apply = await _customer_balance(db, cid)

    # Apply the CN via a payment record (the canonical surface that
    # invokes apply_credit_note_to_invoice). The schema requires
    # amount > 0, so we pair the CN with a token ₹1 cash payment and
    # account for that ₹1 in the assertion.
    pay = await http_client.post(
        "/api/payments",
        json={
            "customer_id": cid,
            "invoice_id": iid,
            "credit_note_id": cn_id,
            "amount": 1,
            "mode": "cash",
        },
        headers=auth_headers,
    )
    assert pay.status_code == 200, pay.text
    assert pay.json()["credit_note_applied"] == 300

    # The ₹1 cash credits the customer by ₹1; the CN application must
    # NOT post any additional customer-ledger entry. Pre-fix this would
    # have credited an extra ₹300 (drifting outstanding by the CN amount).
    assert await _customer_balance(db, cid) == balance_before_apply - 1

    # And the invoice now reflects both the CN and the ₹1 cash.
    invoice = await db.invoices.find_one({"id": iid})
    assert invoice["paid_amount"] == 301
    assert invoice["status"] == "partially_paid"
    assert invoice.get("credit_note_applied") == 300


@pytest.mark.asyncio
async def test_full_cn_plus_cash_clears_invoice(http_client, auth_headers, db):
    """End-to-end: CN ₹300 + cash ₹700 fully pays a ₹1000 invoice and
    leaves the customer ledger at zero outstanding."""
    cid = await _make_customer(http_client, auth_headers, "CN-Full")
    iid = await _make_invoice(http_client, auth_headers, cid, 1000, "CN-Full")

    cn = await http_client.post(
        "/api/credit-notes",
        json={
            "customer_id": cid,
            "invoice_id": iid,
            "items": [{"description": "return", "quantity": 1, "rate": 300}],
            "reason": "damaged",
        },
        headers=auth_headers,
    )
    assert cn.status_code == 200
    cn_id = cn.json()["id"]

    pay = await http_client.post(
        "/api/payments",
        json={
            "customer_id": cid,
            "invoice_id": iid,
            "credit_note_id": cn_id,
            "amount": 700,
            "mode": "cash",
        },
        headers=auth_headers,
    )
    assert pay.status_code == 200

    invoice = await db.invoices.find_one({"id": iid})
    assert invoice["paid_amount"] == 1000
    assert invoice["status"] == "paid"
    assert await _customer_balance(db, cid) == 0.0
