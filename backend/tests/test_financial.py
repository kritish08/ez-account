"""Balance-sheet and trial-balance correctness.

These are the reports an owner reads to decide whether the business is
solvent, so a silently-wrong number here is worse than a crash.
"""

import pytest


async def _make_product(http_client, auth_headers, *, name, cost_price, selling_price):
    resp = await http_client.post(
        "/api/products",
        headers=auth_headers,
        json={
            "name": name,
            "selling_price": selling_price,
            "cost_price": cost_price,
            "item_type": "FINISHED_GOOD",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _make_purchase(http_client, auth_headers, *, product_id, quantity, cost_price):
    resp = await http_client.post(
        "/api/purchases",
        headers=auth_headers,
        json={
            "items": [
                {"product_id": product_id, "quantity": quantity, "cost_price": cost_price}
            ],
            "payment_status": "cash",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_balance_sheet_values_inventory_from_stock_on_hand(http_client, auth_headers):
    """Buying 100 units at Rs.50 must show Rs.5,000 of inventory as an asset.

    Regression: the report read a `stock` field off the product document,
    but no product doc has one — live stock is derived from
    stock_movements. Inventory was therefore always 0, understating total
    assets by the entire value of the warehouse.
    """
    product_id = await _make_product(
        http_client, auth_headers, name="Flour 10kg", cost_price=50, selling_price=80
    )
    await _make_purchase(
        http_client, auth_headers, product_id=product_id, quantity=100, cost_price=50
    )

    resp = await http_client.get("/api/reports/balance-sheet", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assets = resp.json()["assets"]

    assert assets["inventory"] == pytest.approx(5000.0)
    assert assets["total"] == pytest.approx(
        assets["cash"] + assets["bank"] + assets["accounts_receivable"] + 5000.0
    )


@pytest.mark.asyncio
async def test_trial_balance_stays_balanced_across_every_write_path(
    http_client, auth_headers
):
    """Double-entry invariant: every debit has an equal credit, always.

    This is the single assertion that catches an entire class of bug —
    any write path that posts one side of an entry without its
    counterpart shows up here as an out-of-balance trial balance, no
    matter which endpoint introduced it.

    The sequence below walks a realistic day: buy stock, sell some,
    take a payment, book an expense, accept a return, return goods to a
    supplier. After each step the books must still balance.
    """
    checkpoints = []

    async def assert_balanced(step: str):
        resp = await http_client.get("/api/reports/trial-balance", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        checkpoints.append((step, body["total_debit"], body["total_credit"]))
        assert body["is_balanced"] is True, (
            f"books went out of balance after {step}: "
            f"debit {body['total_debit']} vs credit {body['total_credit']}"
        )

    product_id = await _make_product(
        http_client, auth_headers, name="Turmeric 500g", cost_price=120, selling_price=180
    )

    supplier = await http_client.post(
        "/api/suppliers", headers=auth_headers, json={"name": "Erode Spice Mills"}
    )
    assert supplier.status_code == 200, supplier.text
    supplier_id = supplier.json()["id"]

    customer = await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Anand Stores"}
    )
    assert customer.status_code == 200, customer.text
    customer_id = customer.json()["id"]

    await assert_balanced("opening")

    purchase = await http_client.post(
        "/api/purchases",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product_id, "quantity": 200, "cost_price": 120}],
            "payment_status": "unpaid",
        },
    )
    assert purchase.status_code == 200, purchase.text
    await assert_balanced("purchase on credit")

    invoice = await http_client.post(
        "/api/invoices",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "items": [
                {
                    "product_id": product_id,
                    "description": "Turmeric 500g",
                    "quantity": 50,
                    "rate": 180,
                }
            ],
        },
    )
    assert invoice.status_code == 200, invoice.text
    invoice_id = invoice.json()["id"]
    await assert_balanced("sale on credit")

    payment = await http_client.post(
        "/api/payments",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "invoice_id": invoice_id,
            "amount": 5000,
            "mode": "cash",
        },
    )
    assert payment.status_code == 200, payment.text
    await assert_balanced("customer payment")

    expense = await http_client.post(
        "/api/expenses",
        headers=auth_headers,
        json={
            "category": "Transport",
            "description": "Tempo hire to market",
            "amount": 1200,
            "mode": "cash",
        },
    )
    assert expense.status_code == 200, expense.text
    await assert_balanced("expense")

    credit_note = await http_client.post(
        "/api/credit-notes",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "invoice_id": invoice_id,
            "items": [
                {
                    "product_id": product_id,
                    "description": "Turmeric 500g",
                    "quantity": 5,
                    "rate": 180,
                }
            ],
            "reason": "Spoiled",
        },
    )
    assert credit_note.status_code == 200, credit_note.text
    await assert_balanced("sales return")

    debit_note = await http_client.post(
        "/api/debit-notes",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product_id, "quantity": 20, "cost_price": 120}],
            "reason": "Short weight",
        },
    )
    assert debit_note.status_code == 200, debit_note.text
    await assert_balanced("purchase return")

    supplier_payment = await http_client.post(
        "/api/supplier-payments",
        headers=auth_headers,
        json={"supplier_id": supplier_id, "amount": 10000, "mode": "bank"},
    )
    assert supplier_payment.status_code == 200, supplier_payment.text
    await assert_balanced("supplier payment")

    assert len(checkpoints) == 8


@pytest.mark.asyncio
async def test_balance_sheet_inventory_drops_when_stock_is_sold(http_client, auth_headers):
    """Selling 40 of 100 units must leave 60 units (Rs.3,000) on the balance sheet."""
    product_id = await _make_product(
        http_client, auth_headers, name="Sugar 1kg", cost_price=50, selling_price=80
    )
    await _make_purchase(
        http_client, auth_headers, product_id=product_id, quantity=100, cost_price=50
    )

    cust = await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Rajesh Traders"}
    )
    assert cust.status_code == 200, cust.text

    inv = await http_client.post(
        "/api/invoices",
        headers=auth_headers,
        json={
            "customer_id": cust.json()["id"],
            "items": [
                {
                    "product_id": product_id,
                    "description": "Sugar 1kg",
                    "quantity": 40,
                    "rate": 80,
                }
            ],
        },
    )
    assert inv.status_code == 200, inv.text

    resp = await http_client.get("/api/reports/balance-sheet", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    assert resp.json()["assets"]["inventory"] == pytest.approx(3000.0)
