"""GST computation.

Indian GST splits a single rate two ways depending on where the goods
go:

- **Intra-state** — supplier and place of supply in the same state. The
  rate splits evenly into CGST (central) and SGST (state).
- **Inter-state** — different states. The whole rate is IGST.

Place of supply for goods is the delivery location, i.e. the customer's
state. A GSTIN encodes its holder's state in its first two characters,
so for a registered party the state is derivable and does not need to be
asked for twice.

Everything here is pure: no database, no request context. That keeps the
rules — which are the part that must not be wrong — directly testable.
"""

from typing import Optional

# GST state codes, as used in the first two characters of a GSTIN.
# 97 is "Other Territory"; 96 is used for foreign country in some returns.
STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
}

# The slabs a shop will actually meet. Not enforced — a rate outside this
# set still computes correctly — but used to offer sensible choices.
COMMON_RATES = [0, 0.25, 3, 5, 12, 18, 28]


def normalize_gstin(gstin: Optional[str]) -> Optional[str]:
    """Upper-case and strip a GSTIN. Returns None for empty input."""
    if not gstin:
        return None
    cleaned = gstin.strip().upper()
    return cleaned or None


def is_valid_gstin(gstin: Optional[str]) -> bool:
    """Structural check: 15 chars, known state code, PAN-shaped body.

    Deliberately structural rather than checksum-verified — a wrong-but-
    well-formed GSTIN is a data-entry problem, whereas "hello" in the
    field is a bug we can catch cheaply. The field previously accepted
    anything at all.
    """
    g = normalize_gstin(gstin)
    if not g or len(g) != 15:
        return False
    if g[:2] not in STATE_CODES:
        return False
    pan = g[2:12]
    if not (pan[:5].isalpha() and pan[5:9].isdigit() and pan[9].isalpha()):
        return False
    return g[12].isalnum() and g[13].isalpha() and g[14].isalnum()


def state_code_from_gstin(gstin: Optional[str]) -> Optional[str]:
    """The two-digit state code a GSTIN encodes, or None if not derivable."""
    g = normalize_gstin(gstin)
    if not g or len(g) < 2:
        return None
    code = g[:2]
    return code if code in STATE_CODES else None


def is_interstate(
    supplier_state_code: Optional[str],
    place_of_supply_code: Optional[str],
) -> bool:
    """Whether a supply crosses a state border.

    When either side is unknown the supply is treated as intra-state.
    That is the right default for a counter sale to an unregistered
    walk-in customer, which is the common case for a shop — and it fails
    towards CGST+SGST, which is what a local sale actually attracts.
    """
    if not supplier_state_code or not place_of_supply_code:
        return False
    return supplier_state_code != place_of_supply_code


def split_rate(gst_rate: float, interstate: bool) -> tuple[float, float, float]:
    """Split a combined rate into (cgst_rate, sgst_rate, igst_rate)."""
    rate = float(gst_rate or 0)
    if rate <= 0:
        return (0.0, 0.0, 0.0)
    if interstate:
        return (0.0, 0.0, rate)
    half = rate / 2
    return (half, half, 0.0)


def compute_line_tax(
    *,
    amount: float,
    gst_rate: float,
    interstate: bool,
    price_includes_tax: bool = False,
) -> dict:
    """Tax for one invoice line.

    `amount` is quantity x rate. With `price_includes_tax` it is the
    gross amount the customer pays and the taxable value is back-computed
    — shops that quote MRP enter inclusive prices, and treating those as
    exclusive would overstate every invoice by the tax.

    CGST and SGST are derived by halving the *rounded* total tax rather
    than rounding each half independently, so the two always add back to
    the tax amount instead of drifting a paisa apart.
    """
    amount = float(amount or 0)
    rate = float(gst_rate or 0)

    if rate <= 0:
        taxable = round(amount, 2)
        return {
            "taxable_value": taxable,
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": 0.0,
            "tax_amount": 0.0,
            "total": taxable,
        }

    if price_includes_tax:
        taxable = round(amount / (1 + rate / 100), 2)
        tax_amount = round(amount - taxable, 2)
    else:
        taxable = round(amount, 2)
        tax_amount = round(taxable * rate / 100, 2)

    if interstate:
        cgst = sgst = 0.0
        igst = tax_amount
    else:
        # Halve the already-rounded total so the parts reconcile exactly.
        cgst = round(tax_amount / 2, 2)
        sgst = round(tax_amount - cgst, 2)
        igst = 0.0

    return {
        "taxable_value": taxable,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "tax_amount": tax_amount,
        "total": round(taxable + tax_amount, 2),
    }
