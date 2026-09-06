"""GST on invoices, end to end.

The module is optional. The first and most important property is that
with GST off, nothing about an invoice changes — an existing business
that never turns this on must not see a single different number.
"""

import pytest

GSTIN_HARYANA = "06AABCU9603R1ZM"
GSTIN_KARNATAKA = "29AABCU9603R1ZX"


async def _set_gst(http_client, headers, enabled):
    resp = await http_client.put(
        "/api/settings/modules",
        headers=headers,
        json={
            "enable_credit_notes": True,
            "enable_debit_notes": True,
            "enable_advanced_ims": False,
            "enable_production": False,
            "enable_gst": enabled,
        },
    )
    assert resp.status_code == 200, resp.text


async def _setup_business(http_client, headers, gstin=GSTIN_HARYANA):
    resp = await http_client.post(
        "/api/business/setup",
        headers=headers,
        json={
            "name": "Kumar Traders",
            "address": "Sector 14, Gurgaon",
            "gstin": gstin,
            "opening_cash": 0,
            "opening_bank": 0,
        },
    )
    assert resp.status_code == 200, resp.text


async def _make_customer(http_client, headers, name, gstin=None):
    payload = {"name": name}
    if gstin:
        payload["gstin"] = gstin
    resp = await http_client.post("/api/customers", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _make_product(http_client, headers, name, gst_rate=None):
    payload = {
        "name": name,
        "selling_price": 1000,
        "cost_price": 600,
        "item_type": "FINISHED_GOOD",
    }
    if gst_rate is not None:
        payload["gst_rate"] = gst_rate
        payload["hsn"] = "1006"
    resp = await http_client.post("/api/products", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _make_invoice(http_client, headers, customer_id, product_id, qty=1, rate=1000):
    resp = await http_client.post(
        "/api/invoices",
        headers=headers,
        json={
            "customer_id": customer_id,
            "items": [
                {
                    "product_id": product_id,
                    "description": "Basmati Rice 25kg",
                    "quantity": qty,
                    "rate": rate,
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _trial_balance(http_client, headers):
    resp = await http_client.get("/api/reports/trial-balance", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_gst_is_off_by_default(http_client, auth_headers):
    """An existing business must not have tax switched on under it."""
    resp = await http_client.get("/api/settings/modules", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["enable_gst"] is False


@pytest.mark.asyncio
async def test_with_gst_off_the_invoice_is_untouched(http_client, auth_headers, db):
    """The whole point of the flag: off means exactly today's behaviour."""
    await _setup_business(http_client, auth_headers)
    cid = await _make_customer(http_client, auth_headers, "Walk-in")
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)

    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)
    inv = await db.invoices.find_one({"id": invoice_id})

    assert inv["total"] == pytest.approx(1000.0)
    assert inv.get("tax_amount", 0) == 0
    assert "gst" not in inv
    assert inv["items"][0].get("cgst", 0) == 0
    # No tax account should exist at all.
    assert await db.ledger.count_documents({"account": "gst_output"}) == 0


@pytest.mark.asyncio
async def test_intrastate_invoice_splits_into_cgst_and_sgst(
    http_client, auth_headers, db
):
    """Haryana business, Haryana customer: 9% + 9%."""
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Local Shop", GSTIN_HARYANA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)

    inv = await db.invoices.find_one({"id": invoice_id})
    assert inv["taxable_value"] == pytest.approx(1000.0)
    assert inv["cgst"] == pytest.approx(90.0)
    assert inv["sgst"] == pytest.approx(90.0)
    assert inv["igst"] == pytest.approx(0.0)
    assert inv["tax_amount"] == pytest.approx(180.0)
    assert inv["total"] == pytest.approx(1180.0)
    assert inv["is_interstate"] is False


@pytest.mark.asyncio
async def test_interstate_invoice_uses_igst(http_client, auth_headers, db):
    """Haryana business, Karnataka customer: 18% IGST."""
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Bengaluru Co", GSTIN_KARNATAKA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)

    inv = await db.invoices.find_one({"id": invoice_id})
    assert inv["cgst"] == pytest.approx(0.0)
    assert inv["sgst"] == pytest.approx(0.0)
    assert inv["igst"] == pytest.approx(180.0)
    assert inv["total"] == pytest.approx(1180.0)
    assert inv["is_interstate"] is True


@pytest.mark.asyncio
async def test_tax_is_posted_to_the_ledger_as_a_liability(
    http_client, auth_headers, db
):
    """Tax collected is owed to the government, not revenue.

    Sales must be credited the taxable value only; the tax goes to its
    own liability account, or the P&L overstates revenue by the tax and
    the balance sheet has no idea money is owed.
    """
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Local Shop", GSTIN_HARYANA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)

    async def balance(account):
        rows = await db.ledger.find({"account": account}).to_list(None)
        return round(sum(r["debit"] for r in rows) - sum(r["credit"] for r in rows), 2)

    # Customer owes the gross amount.
    assert await balance(f"customer:{cid}") == pytest.approx(1180.0)
    # Revenue is the taxable value only.
    assert await balance("sales") == pytest.approx(-1000.0)
    # Tax collected sits in its own liability account (credit nature).
    assert await balance("gst_output") == pytest.approx(-180.0)


@pytest.mark.asyncio
async def test_trial_balance_holds_with_gst_on(http_client, auth_headers):
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Local Shop", GSTIN_HARYANA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    await _make_invoice(http_client, auth_headers, cid, pid, 3, 1250)

    body = await _trial_balance(http_client, auth_headers)
    assert body["is_balanced"] is True, (
        f"debit {body['total_debit']} vs credit {body['total_credit']}"
    )


@pytest.mark.asyncio
async def test_line_items_carry_their_own_tax_breakdown(http_client, auth_headers, db):
    """Rule 46 requires per-line rate, taxable value and tax on the invoice."""
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Local Shop", GSTIN_HARYANA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=5)
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 2, 400)

    line = (await db.invoices.find_one({"id": invoice_id}))["items"][0]
    assert line["gst_rate"] == pytest.approx(5.0)
    assert line["hsn"] == "1006"
    assert line["taxable_value"] == pytest.approx(800.0)
    assert line["cgst"] == pytest.approx(20.0)
    assert line["sgst"] == pytest.approx(20.0)
    assert line["amount"] == pytest.approx(840.0)


@pytest.mark.asyncio
async def test_a_zero_rated_product_attracts_no_tax(http_client, auth_headers, db):
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Local Shop", GSTIN_HARYANA)
    pid = await _make_product(http_client, auth_headers, "Fresh Milk", gst_rate=0)
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 1, 60)

    inv = await db.invoices.find_one({"id": invoice_id})
    assert inv["tax_amount"] == pytest.approx(0.0)
    assert inv["total"] == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_unregistered_customer_is_treated_as_a_local_sale(
    http_client, auth_headers, db
):
    """A walk-in with no GSTIN is a counter sale: CGST + SGST."""
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Walk-in")
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)

    inv = await db.invoices.find_one({"id": invoice_id})
    assert inv["is_interstate"] is False
    assert inv["cgst"] == pytest.approx(90.0)
    assert inv["igst"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_turning_gst_off_again_stops_taxing_new_invoices(
    http_client, auth_headers, db
):
    """The flag is a real switch, not a one-way door."""
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Local Shop", GSTIN_HARYANA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    taxed = await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)

    await _set_gst(http_client, auth_headers, False)
    untaxed = await _make_invoice(http_client, auth_headers, cid, pid, 1, 1000)

    assert (await db.invoices.find_one({"id": taxed}))["total"] == pytest.approx(1180.0)
    assert (await db.invoices.find_one({"id": untaxed}))["total"] == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_invalid_gstin_is_rejected(http_client, auth_headers):
    """The field previously accepted any string at all, including 'hello'."""
    resp = await http_client.post(
        "/api/customers", headers=auth_headers, json={"name": "Bad", "gstin": "hello"}
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_a_valid_gstin_is_accepted_and_normalized(http_client, auth_headers, db):
    resp = await http_client.post(
        "/api/customers",
        headers=auth_headers,
        json={"name": "Good", "gstin": "  06aabcu9603r1zm  "},
    )
    assert resp.status_code == 200, resp.text
    doc = await db.customers.find_one({"id": resp.json()["id"]})
    assert doc["gstin"] == GSTIN_HARYANA


@pytest.mark.asyncio
async def test_pdf_renders_for_a_gst_invoice(http_client, auth_headers):
    """The PDF path has extra branches under GST — make sure it doesn't 500.

    reportlab output is compressed, so this asserts the endpoint renders a
    real PDF rather than grepping for the tax rows; the numbers themselves
    are pinned by the tests above.
    """
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    await _set_gst(http_client, auth_headers, True)

    cid = await _make_customer(http_client, auth_headers, "Bengaluru Co", GSTIN_KARNATAKA)
    pid = await _make_product(http_client, auth_headers, "Rice", gst_rate=18)
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 2, 1500)

    resp = await http_client.get(f"/api/invoices/{invoice_id}/pdf", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 1000


@pytest.mark.asyncio
async def test_pdf_still_renders_without_gst(http_client, auth_headers):
    """The non-GST branch must keep working untouched."""
    await _setup_business(http_client, auth_headers, GSTIN_HARYANA)
    cid = await _make_customer(http_client, auth_headers, "Walk-in")
    pid = await _make_product(http_client, auth_headers, "Rice")
    invoice_id = await _make_invoice(http_client, auth_headers, cid, pid, 1, 500)

    resp = await http_client.get(f"/api/invoices/{invoice_id}/pdf", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"%PDF"
