"""Trial Balance and Balance Sheet.

Both endpoints originally lived in the "PHASE 3" section of server.py.
They sit here together because they share the same double-entry
derivation logic and the same ledger-aggregation pattern.

REMOVED: `POST /api/maintenance/fix-ledger`. It was a one-time migration
to back-fill double-entry pairs for docs created before the v2 ledger
conventions, and it described itself as idempotent and safe to re-run.
It was neither, once the write paths moved on:

- Its "already posted?" test matched only ledger rows whose debit/credit
  exactly equalled `payment.amount`. `record_payment` splits a payment
  into an applied portion plus an advance, so neither row matched and it
  posted a THIRD customer credit for the full amount — over-crediting the
  customer on every payment that had any excess.
- It created `purchases` account debits that no live code path writes
  (purchases debit `inventory_asset`), leaving an unbalanced debit that
  the balance sheet then double-counted into COGS.

It had no caller in the frontend or anywhere else. Restoring it means
rewriting the exists-checks against current conventions and gating it
behind a dry-run — not reverting this deletion.
"""

import asyncio

from fastapi import APIRouter, Depends

from app.database import db
from app.deps import get_current_user
from app.services.stock import get_all_product_stock

router = APIRouter(prefix="/api", tags=["financial"])


@router.get("/reports/trial-balance")
async def get_trial_balance(current_user: dict = Depends(get_current_user)):
    """Trial Balance (sum of distinct accounts)."""
    pipeline = [
        {"$group": {
            "_id": "$account",
            "debit": {"$sum": "$debit"},
            "credit": {"$sum": "$credit"}
        }},
        {"$project": {
            "account": "$_id",
            "debit": 1,
            "credit": 1,
            "balance": {"$subtract": ["$debit", "$credit"]},
            "_id": 0
        }},
        {"$sort": {"account": 1}}
    ]

    entries = await db.ledger.aggregate(pipeline).to_list(None)

    total_debit = sum(e["debit"] for e in entries)
    total_credit = sum(e["credit"] for e in entries)

    return {
        "entries": entries,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": abs(total_debit - total_credit) < 0.01
    }


@router.get("/reports/balance-sheet")
async def get_balance_sheet(current_user: dict = Depends(get_current_user)):
    """Balance Sheet (Assets, Liabilities, Equity).

    The system uses periodic-inventory accounting: COGS is computed
    from purchases + change-in-stock at report time rather than on
    every sale. Equity = Capital + Net Profit, where Net Profit is
    derived back from the ledger so the equation balances.
    """
    pipeline = [
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}}
        }}
    ]
    balances = {doc["_id"]: doc["balance"] for doc in await db.ledger.aggregate(pipeline).to_list(None)}

    def get_bal(key):
        return balances.get(key, 0)

    def get_prefix_sum(prefix):
        return sum(v for k, v in balances.items() if k.startswith(prefix))

    cash = get_bal("cash")
    bank = get_bal("bank")
    accounts_receivable = get_prefix_sum("customer:")

    # Inventory: cost_price * stock-on-hand summed across products. In a
    # pure double-entry system this would live on the ledger; here it's
    # tracked separately for simplicity and reconciled into Equity
    # via Net Profit so the equation still balances.
    #
    # Stock is DERIVED from stock_movements — product documents carry no
    # live `stock` field (`stock_quantity` is only the opening figure).
    # Reading a non-existent field here made inventory permanently 0,
    # understating total assets by the whole value of the warehouse.
    products, stock_map = await asyncio.gather(
        db.products.find({}, {"_id": 0, "id": 1, "cost_price": 1}).to_list(None),
        get_all_product_stock(),
    )
    inventory_value = sum(
        (p.get("cost_price", 0) or 0) * (stock_map.get(p["id"], 0) or 0) for p in products
    )

    total_assets = cash + bank + accounts_receivable + inventory_value

    # Liability accounts have credit-nature, so (debit - credit) is
    # negative when we owe money — flip the sign for presentation.
    accounts_payable_raw = get_prefix_sum("supplier:")
    accounts_payable = -accounts_payable_raw

    customer_credits_raw = get_prefix_sum("customer_credit:")
    customer_credits = -customer_credits_raw

    total_liabilities = accounts_payable + customer_credits

    # Income (credit nature) → flip sign so positive sales come out positive.
    sales = -get_bal("sales")

    purchases = get_bal("purchases")
    expenses_total = get_prefix_sum("expense:")

    # COGS = Opening Stock + Purchases - Closing Stock.
    # No date filter here — this is an as-of-today snapshot so opening
    # stock is treated as zero.
    opening_stock = 0
    closing_stock = inventory_value

    cost_of_goods_sold = opening_stock + purchases - closing_stock
    gross_profit = sales - cost_of_goods_sold
    net_profit = gross_profit - expenses_total

    capital = -get_bal("capital")
    total_equity = net_profit + capital

    return {
        "assets": {
            "cash": cash,
            "bank": bank,
            "accounts_receivable": accounts_receivable,
            "inventory": inventory_value,
            "total": total_assets
        },
        "liabilities": {
            "accounts_payable": accounts_payable,
            "customer_credits": customer_credits,
            "total": total_liabilities
        },
        "equity": {
            "net_profit": net_profit,
            "total": total_equity
        },
        "is_balanced": abs(total_assets - (total_liabilities + total_equity)) < 1.0
    }
