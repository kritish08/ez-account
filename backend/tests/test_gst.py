"""GST computation.

Pure functions, so the rules are pinned precisely. Getting these wrong
means every invoice a registered dealer issues is non-compliant, and the
recipient cannot claim input credit from it.

Rules encoded here:
  - Intra-state supply (supplier state == place of supply): the rate
    splits evenly into CGST + SGST.
  - Inter-state supply: the whole rate is IGST.
  - A GSTIN's first two characters are the state code, so place of supply
    is derivable for registered parties.
"""

import pytest

from app.services.gst import (
    compute_line_tax,
    is_interstate,
    normalize_gstin,
    split_rate,
    state_code_from_gstin,
)

# Real-format GSTINs: 2-digit state, 10-char PAN, entity, 'Z', checksum.
GSTIN_HARYANA = "06AABCU9603R1ZM"
GSTIN_KARNATAKA = "29AABCU9603R1ZX"


class TestStateCode:
    def test_extracts_state_code_from_gstin(self):
        assert state_code_from_gstin(GSTIN_HARYANA) == "06"
        assert state_code_from_gstin(GSTIN_KARNATAKA) == "29"

    def test_returns_none_for_missing_or_malformed(self):
        assert state_code_from_gstin(None) is None
        assert state_code_from_gstin("") is None
        assert state_code_from_gstin("hello") is None
        assert state_code_from_gstin("99AABCU9603R1ZM") is None  # not a real state

    def test_normalizes_case_and_whitespace(self):
        assert normalize_gstin("  06aabcu9603r1zm ") == GSTIN_HARYANA


class TestInterstate:
    def test_same_state_is_intrastate(self):
        assert is_interstate("06", "06") is False

    def test_different_state_is_interstate(self):
        assert is_interstate("06", "29") is True

    def test_unknown_place_of_supply_defaults_to_intrastate(self):
        """An unregistered walk-in customer with no state recorded is
        treated as local, which is the correct default for a counter sale."""
        assert is_interstate("06", None) is False


class TestRateSplit:
    def test_intrastate_splits_evenly(self):
        assert split_rate(18, interstate=False) == (9.0, 9.0, 0.0)

    def test_interstate_is_all_igst(self):
        assert split_rate(18, interstate=True) == (0.0, 0.0, 18.0)

    def test_odd_rate_splits_to_halves(self):
        assert split_rate(5, interstate=False) == (2.5, 2.5, 0.0)

    def test_zero_rate(self):
        assert split_rate(0, interstate=False) == (0.0, 0.0, 0.0)


class TestLineTaxExclusive:
    """Default: the entered rate is the pre-tax price."""

    def test_intrastate_18_percent(self):
        r = compute_line_tax(amount=1000, gst_rate=18, interstate=False)
        assert r["taxable_value"] == pytest.approx(1000.0)
        assert r["cgst"] == pytest.approx(90.0)
        assert r["sgst"] == pytest.approx(90.0)
        assert r["igst"] == pytest.approx(0.0)
        assert r["tax_amount"] == pytest.approx(180.0)
        assert r["total"] == pytest.approx(1180.0)

    def test_interstate_18_percent(self):
        r = compute_line_tax(amount=1000, gst_rate=18, interstate=True)
        assert r["cgst"] == pytest.approx(0.0)
        assert r["sgst"] == pytest.approx(0.0)
        assert r["igst"] == pytest.approx(180.0)
        assert r["total"] == pytest.approx(1180.0)

    def test_zero_rated_supply(self):
        r = compute_line_tax(amount=500, gst_rate=0, interstate=False)
        assert r["tax_amount"] == pytest.approx(0.0)
        assert r["taxable_value"] == pytest.approx(500.0)
        assert r["total"] == pytest.approx(500.0)

    def test_components_always_sum_to_the_tax_amount(self):
        for rate in (0, 0.25, 3, 5, 12, 18, 28):
            for interstate in (True, False):
                r = compute_line_tax(amount=1337.77, gst_rate=rate, interstate=interstate)
                assert r["cgst"] + r["sgst"] + r["igst"] == pytest.approx(
                    r["tax_amount"], abs=0.01
                ), f"rate={rate} interstate={interstate}"
                assert r["taxable_value"] + r["tax_amount"] == pytest.approx(
                    r["total"], abs=0.01
                )


class TestLineTaxInclusive:
    """Shops that quote MRP enter a tax-inclusive price.

    Treating an inclusive price as exclusive overstates every invoice by
    the tax amount, so this has to be a supported mode rather than an
    assumption.
    """

    def test_intrastate_back_computes_taxable_value(self):
        r = compute_line_tax(
            amount=1180, gst_rate=18, interstate=False, price_includes_tax=True
        )
        assert r["taxable_value"] == pytest.approx(1000.0, abs=0.01)
        assert r["cgst"] == pytest.approx(90.0, abs=0.01)
        assert r["sgst"] == pytest.approx(90.0, abs=0.01)
        assert r["total"] == pytest.approx(1180.0, abs=0.01)

    def test_total_equals_the_entered_amount(self):
        """The whole point: what the customer is charged is what was typed."""
        for rate in (5, 12, 18, 28):
            r = compute_line_tax(
                amount=999, gst_rate=rate, interstate=False, price_includes_tax=True
            )
            assert r["total"] == pytest.approx(999.0, abs=0.01), f"rate={rate}"

    def test_zero_rate_inclusive_is_a_no_op(self):
        r = compute_line_tax(
            amount=750, gst_rate=0, interstate=False, price_includes_tax=True
        )
        assert r["taxable_value"] == pytest.approx(750.0)
        assert r["tax_amount"] == pytest.approx(0.0)


class TestRounding:
    def test_values_are_rounded_to_paise(self):
        r = compute_line_tax(amount=333.33, gst_rate=18, interstate=False)
        for key in ("taxable_value", "cgst", "sgst", "igst", "tax_amount", "total"):
            assert round(r[key], 2) == r[key], f"{key} carries sub-paise precision"

    def test_half_rate_rounding_does_not_lose_a_paisa(self):
        """CGST and SGST are each half the tax; rounding both must still
        add up to the total tax, not one paisa short."""
        r = compute_line_tax(amount=105.05, gst_rate=5, interstate=False)
        assert r["cgst"] + r["sgst"] == pytest.approx(r["tax_amount"], abs=0.001)
