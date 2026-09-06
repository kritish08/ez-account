"""Product update semantics.

`cost_price` feeds COGS on every sale and the inventory valuation on the
balance sheet, so silently resetting it corrupts profit reporting for
that SKU from then on.
"""

import pytest


async def _make_product(http_client, auth_headers, **overrides):
    payload = {
        "name": "Basmati Rice 5kg",
        "selling_price": 480,
        "cost_price": 350,
        "low_stock_threshold": 25,
        "item_type": "FINISHED_GOOD",
        "track_batches": True,
    }
    payload.update(overrides)
    resp = await http_client.post("/api/products", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_partial_update_preserves_fields_not_sent(http_client, auth_headers):
    """Renaming a product must not reset every field the client omitted.

    Regression: the handler typed its body as ProductCreate (where
    cost_price defaults to 0) and $set the full model_dump(), so a
    two-field edit silently zeroed cost_price, reset the low-stock
    threshold to 10 and turned batch tracking off.
    """
    product_id = await _make_product(http_client, auth_headers)

    resp = await http_client.put(
        f"/api/products/{product_id}",
        headers=auth_headers,
        json={"name": "Basmati Rice 5kg (Premium)"},
    )
    assert resp.status_code == 200, resp.text

    got = await http_client.get(f"/api/products/{product_id}", headers=auth_headers)
    assert got.status_code == 200, got.text
    product = got.json()

    assert product["name"] == "Basmati Rice 5kg (Premium)"
    assert product["cost_price"] == pytest.approx(350.0)
    assert product["selling_price"] == pytest.approx(480.0)
    assert product["low_stock_threshold"] == pytest.approx(25.0)
    assert product["track_batches"] is True


@pytest.mark.asyncio
async def test_update_still_applies_fields_that_are_sent(http_client, auth_headers):
    """A partial update must not become a no-op — sent fields still land."""
    product_id = await _make_product(http_client, auth_headers)

    resp = await http_client.put(
        f"/api/products/{product_id}",
        headers=auth_headers,
        json={"cost_price": 375, "low_stock_threshold": 40},
    )
    assert resp.status_code == 200, resp.text

    product = (
        await http_client.get(f"/api/products/{product_id}", headers=auth_headers)
    ).json()

    assert product["cost_price"] == pytest.approx(375.0)
    assert product["low_stock_threshold"] == pytest.approx(40.0)
    assert product["name"] == "Basmati Rice 5kg"


@pytest.mark.asyncio
async def test_update_can_explicitly_set_cost_price_to_zero(http_client, auth_headers):
    """Sending cost_price=0 deliberately must still work — 0 is a real value."""
    product_id = await _make_product(http_client, auth_headers)

    resp = await http_client.put(
        f"/api/products/{product_id}",
        headers=auth_headers,
        json={"cost_price": 0},
    )
    assert resp.status_code == 200, resp.text

    product = (
        await http_client.get(f"/api/products/{product_id}", headers=auth_headers)
    ).json()

    assert product["cost_price"] == pytest.approx(0.0)
