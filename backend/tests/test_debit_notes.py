"""Debit notes (purchase returns).

A purchase debits `inventory_asset`; returning those goods to the
supplier has to credit it back, or the asset side of the balance sheet
drifts upward permanently with every return.
"""

import pytest


async def _seed(http_client, auth_headers):
    prod = await http_client.post(
        "/api/products",
        headers=auth_headers,
        json={
            "name": "Cement Bag 50kg",
            "selling_price": 420,
            "cost_price": 350,
            "item_type": "RAW_MATERIAL",
        },
    )
    assert prod.status_code == 200, prod.text
    product_id = prod.json()["id"]

    sup = await http_client.post(
        "/api/suppliers", headers=auth_headers, json={"name": "Ambuja Depot"}
    )
    assert sup.status_code == 200, sup.text
    supplier_id = sup.json()["id"]

    purchase = await http_client.post(
        "/api/purchases",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product_id, "quantity": 100, "cost_price": 350}],
            "payment_status": "unpaid",
        },
    )
    assert purchase.status_code == 200, purchase.text
    return product_id, supplier_id


async def _account_balance(db, account):
    rows = await db.ledger.find({"account": account}).to_list(None)
    return sum(r["debit"] for r in rows) - sum(r["credit"] for r in rows)


@pytest.mark.asyncio
async def test_purchase_return_credits_inventory_asset(http_client, auth_headers, db):
    """Returning 40 of 100 bags must reduce inventory_asset by their cost.

    Regression: the debit note moved stock out and reduced the supplier
    payable, but credited a `purchases_returns` account instead of
    `inventory_asset`. Inventory stayed booked at the full purchase value
    against physically fewer goods, and the overstatement compounded with
    every return.
    """
    product_id, supplier_id = await _seed(http_client, auth_headers)

    assert await _account_balance(db, "inventory_asset") == pytest.approx(35000.0)

    dn = await http_client.post(
        "/api/debit-notes",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product_id, "quantity": 40, "cost_price": 350}],
            "reason": "Damaged in transit",
        },
    )
    assert dn.status_code == 200, dn.text

    # 60 bags left on hand at Rs.350.
    assert await _account_balance(db, "inventory_asset") == pytest.approx(21000.0)
    # Payable reduced by the returned value (credit-nature, so negative).
    assert await _account_balance(db, f"supplier:{supplier_id}") == pytest.approx(-21000.0)


@pytest.mark.asyncio
async def test_purchase_return_keeps_the_trial_balance_balanced(
    http_client, auth_headers, db
):
    """Every entry the debit note writes must have a counterpart."""
    product_id, supplier_id = await _seed(http_client, auth_headers)

    dn = await http_client.post(
        "/api/debit-notes",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product_id, "quantity": 40, "cost_price": 350}],
        },
    )
    assert dn.status_code == 200, dn.text

    resp = await http_client.get("/api/reports/trial-balance", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_balanced"] is True, (
        f"debit {body['total_debit']} != credit {body['total_credit']}"
    )


@pytest.mark.asyncio
async def test_balance_sheet_inventory_matches_stock_after_a_return(
    http_client, auth_headers
):
    """The ledger asset and the physical valuation must agree after a return."""
    product_id, supplier_id = await _seed(http_client, auth_headers)

    dn = await http_client.post(
        "/api/debit-notes",
        headers=auth_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": product_id, "quantity": 40, "cost_price": 350}],
        },
    )
    assert dn.status_code == 200, dn.text

    resp = await http_client.get("/api/reports/balance-sheet", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    assert resp.json()["assets"]["inventory"] == pytest.approx(21000.0)
