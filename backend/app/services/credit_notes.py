"""Credit-note value helpers.

A credit note carries two distinct amounts, and conflating them was the
root cause of three separate book-keeping bugs:

- **face value** (`total`) — what was returned. Immutable once issued.
  This is what sales/P&L reports and the dashboard must count.
- **remaining balance** (`remaining_amount`) — how much credit is still
  spendable. Decremented as the note is applied to invoices.

Originally a single `total` field served both: written as the face value
at issue, then `$inc`'d downward on application. Consumers reading it as
"the amount of this credit note" silently went wrong the moment a note
was applied — applied returns vanished from the P&L, and editing a
partly-spent note re-issued the credit that had already been used.

`face_value` / `remaining` read either shape, so notes written before
the split keep working: in a legacy document `total` holds the *remaining*
balance, and the true face value is recoverable from the line items.
"""


def face_value(cn: dict) -> float:
    """The note's original amount — what was actually returned."""
    if "remaining_amount" in cn:
        return cn.get("total", 0) or 0
    # Legacy doc: `total` was decremented on application, so recover the
    # issued amount from the line items it was computed from.
    items = cn.get("items") or []
    if items:
        return round(sum(i.get("amount", 0) or 0 for i in items), 2)
    return cn.get("total", 0) or 0


def remaining(cn: dict) -> float:
    """Credit still available to apply to invoices."""
    if "remaining_amount" in cn:
        return cn.get("remaining_amount", 0) or 0
    # Legacy doc: `total` already held the remaining balance.
    return cn.get("total", 0) or 0
