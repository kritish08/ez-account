"""Money rounding helper.

Single source of truth for the `_money()` rule. Apply at every
multiplication / boundary in money math. See `MONEY-ROUNDING` in
FIXES.md for the rationale.
"""


def _money(x) -> float:
    """Round a monetary value to 2 decimal places.

    Per-line values are rounded to 2 dp; running totals then accumulate
    already-rounded values exactly. This produces the same numerical
    result as Python's `Decimal` for 2-dp INR accounting without
    requiring a stored-data migration to Decimal128.

    Floats give known errors like `0.1 + 0.2 == 0.30000000000000004`.
    Without this helper, an invoice with many decimal-priced lines could
    end with a total like 999.9999999... that fails a
    `paid_amount >= total` check by a cent and never marks the invoice
    as paid.
    """
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return 0.0
