"""Invoice publish lifecycle.

Publishing is the point where a draft becomes real money: it posts the
customer-AR debit, the sales credit, and the stock-out movements. Doing
that twice is unrecoverable without a manual ledger repair.
"""

import asyncio

import pytest


async def _seed_draft(http_client, auth_headers, *, quantity=10, rate=100):
    prod = await http_client.post(
        "/api/products",
        headers=auth_headers,
        json={
            "name": "Steel Bolt M8",
            "selling_price": rate,
            "cost_price": 40,
            "item_type": "FINISHED_GOOD",
        },
    )
    assert prod.status_code == 200, prod.text
    product_id = prod.json()["id"]

    await http_client.post(
        "/api/purchases",
        headers=auth_headers,
        json={
            "items": [{"product_id": product_id, "quantity": 500, "cost_price": 40}],
            "payment_status": "cash",
        },
    )

    cust = await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Kumar Hardware"}
    )
    assert cust.status_code == 200, cust.text

    inv = await http_client.post(
        "/api/invoices",
        headers=auth_headers,
        json={
            "customer_id": cust.json()["id"],
            "is_draft": True,
            "items": [
                {
                    "product_id": product_id,
                    "description": "Steel Bolt M8",
                    "quantity": quantity,
                    "rate": rate,
                }
            ],
        },
    )
    assert inv.status_code == 200, inv.text
    return inv.json()["id"], product_id


@pytest.mark.asyncio
async def test_publishing_a_draft_posts_revenue_once(http_client, auth_headers, db):
    """The happy path: one publish, one sales credit, one stock-out."""
    invoice_id, product_id = await _seed_draft(http_client, auth_headers)

    resp = await http_client.post(
        f"/api/invoices/{invoice_id}/publish", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    sales = await db.ledger.find({"ref_id": invoice_id, "account": "sales"}).to_list(None)
    assert len(sales) == 1
    assert sales[0]["credit"] == pytest.approx(1000.0)

    movements = await db.stock_movements.find(
        {"ref_id": invoice_id, "ref_type": "invoice"}
    ).to_list(None)
    assert len(movements) == 1
    assert movements[0]["quantity_out"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_concurrent_publish_posts_revenue_exactly_once(
    http_client, auth_headers, db
):
    """Two simultaneous publishes must not double-post revenue or stock.

    Regression: the handler read the invoice, checked status != draft,
    then did three awaits of ledger and stock writes BEFORE flipping the
    status. Both requests passed the guard, so a double-click credited
    sales twice and decremented stock twice with no error shown.
    """
    invoice_id, product_id = await _seed_draft(http_client, auth_headers)

    first, second = await asyncio.gather(
        http_client.post(f"/api/invoices/{invoice_id}/publish", headers=auth_headers),
        http_client.post(f"/api/invoices/{invoice_id}/publish", headers=auth_headers),
        return_exceptions=True,
    )

    statuses = sorted(
        r.status_code for r in (first, second) if not isinstance(r, Exception)
    )
    assert statuses == [200, 400], f"expected one success and one rejection, got {statuses}"

    sales = await db.ledger.find({"ref_id": invoice_id, "account": "sales"}).to_list(None)
    assert len(sales) == 1, f"revenue posted {len(sales)} times"

    ar = await db.ledger.find(
        {"ref_id": invoice_id, "account": {"$regex": "^customer:"}}
    ).to_list(None)
    assert len(ar) == 1, f"customer AR posted {len(ar)} times"

    movements = await db.stock_movements.find(
        {"ref_id": invoice_id, "ref_type": "invoice"}
    ).to_list(None)
    assert len(movements) == 1, f"stock moved {len(movements)} times"


@pytest.mark.asyncio
async def test_publishing_an_already_published_invoice_is_rejected(
    http_client, auth_headers
):
    """Sequential re-publish still returns 400."""
    invoice_id, _ = await _seed_draft(http_client, auth_headers)

    first = await http_client.post(
        f"/api/invoices/{invoice_id}/publish", headers=auth_headers
    )
    assert first.status_code == 200, first.text

    second = await http_client.post(
        f"/api/invoices/{invoice_id}/publish", headers=auth_headers
    )
    assert second.status_code == 400
