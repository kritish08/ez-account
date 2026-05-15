"""Trial Balance, Balance Sheet, and the one-shot ledger-fix migration.

These three endpoints originally lived in the "PHASE 3" section of
server.py. They sit here together because they share the same
double-entry derivation logic and the same ledger-aggregation pattern.

`fix_ledger_data` is a one-time migration to back-fill double-entry
pairs for historical docs created before the v2 ledger conventions
landed. It's idempotent (each entry has an exists-check) and safe to
re-run.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.database import db
from app.deps import get_current_user
from app.services.ledger import create_ledger_entry

router = APIRouter(prefix="/api", tags=["financial"])


@router.post("/maintenance/fix-ledger")
async def fix_ledger_data(current_user: dict = Depends(get_current_user)):
    """One-time fix to ensure double-entry bookkeeping for historical data."""
    fixed_counts = {"invoices": 0, "purchases": 0, "expenses": 0}

    # 1. Fix Invoices (Credit Sales)
    invoices = await db.invoices.find({"status": {"$ne": "draft"}}).to_list(None)
    for inv in invoices:
        exists = await db.ledger.find_one({
            "ref_id": inv["id"],
            "account": "sales"
        })
        if not exists:
            await create_ledger_entry(
                account="sales",
                debit=0,
                credit=inv["total"],
                narration=f"Invoice {inv['invoice_number']} (Retroactive Fix)",
                ref_type="invoice",
                ref_id=inv["id"],
                date=inv["date"]
            )
            fixed_counts["invoices"] += 1

    # 2. Fix Purchases (Debit Purchases)
    purchases = await db.purchases.find({}).to_list(None)
    for pur in purchases:
        exists = await db.ledger.find_one({
            "ref_id": pur["id"],
            "account": "purchases"
        })
        if not exists:
            await create_ledger_entry(
                account="purchases",
                debit=pur["total"],
                credit=0,
                narration=f"Purchase {pur['purchase_number']} (Retroactive Fix)",
                ref_type="purchase",
                ref_id=pur["id"],
                date=pur["date"]
            )
            fixed_counts["purchases"] += 1

    # 3. Fix Expenses (Debit Expense Category)
    expenses = await db.expenses.find({}).to_list(None)
    for exp in expenses:
        exists = await db.ledger.find_one({
            "ref_id": exp["id"],
            "account": {"$regex": "^expense:"}
        })
        if not exists:
            await create_ledger_entry(
                account=f"expense:{exp['category']}",
                debit=exp["amount"],
                credit=0,
                narration=f"Expense: {exp['description']} (Retroactive Fix)",
                ref_type="expense",
                ref_id=exp["id"],
                date=exp["date"]
            )
            fixed_counts["expenses"] += 1

    # 4. Fix Setup (Credit Capital)
    business = await db.business.find_one({})
    if business:
        if business.get("opening_cash", 0) > 0:
            exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "narration": "Opening capital (cash)"})
            if not exists:
                await create_ledger_entry("capital", 0, business["opening_cash"], "Opening capital (cash)", "setup", business["id"], business.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
                fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1

        if business.get("opening_bank", 0) > 0:
            exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "narration": "Opening capital (bank)"})
            if not exists:
                await create_ledger_entry("capital", 0, business["opening_bank"], "Opening capital (bank)", "setup", business["id"], business.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
                fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1

    # 5. Fix Supplier Opening Balance (Debit Capital)
    suppliers = await db.suppliers.find({"opening_balance": {"$gt": 0}}).to_list(None)
    for sup in suppliers:
        exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "ref_id": sup["id"]})
        if not exists:
            # Liability -> Debit Capital
            await create_ledger_entry("capital", sup["opening_balance"], 0, "Opening capital (supplier)", "setup", sup["id"], sup.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1

    # 6. Fix Customer Opening Balance
    customers = await db.customers.find({"opening_balance": {"$gt": 0}}).to_list(None)
    for cust in customers:
        exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "ref_id": cust["id"]})
        if not exists:
            if cust.get("balance_type", "debit") == "debit":
                # Asset -> Credit Capital
                await create_ledger_entry("capital", 0, cust["opening_balance"], "Opening capital (customer)", "setup", cust["id"], cust.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            else:
                # Liability -> Debit Capital
                await create_ledger_entry("capital", cust["opening_balance"], 0, "Opening capital (customer)", "setup", cust["id"], cust.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1

    # 7. Fix Payments (Debit Cash/Bank, Credit Customer)
    payments = await db.payments.find({}).to_list(None)
    for pay in payments:
        exists_dr = await db.ledger.find_one({"ref_type": "payment", "ref_id": pay["id"], "debit": pay["amount"]})
        if not exists_dr:
            await create_ledger_entry(pay["mode"], pay["amount"], 0, f"Payment from {pay['customer_name']}", "payment", pay["id"], pay["date"])
            fixed_counts["payments"] = fixed_counts.get("payments", 0) + 1

        exists_cr = await db.ledger.find_one({"ref_type": "payment", "ref_id": pay["id"], "credit": pay["amount"]})
        if not exists_cr:
            await create_ledger_entry(f"customer:{pay['customer_id']}", 0, pay["amount"], "Payment received", "payment", pay["id"], pay["date"])
            fixed_counts["payments"] = fixed_counts.get("payments", 0) + 1

    return {"message": "Ledger fixed successfully", "counts": fixed_counts}


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

    # Inventory: cost_price * stock summed from products. In a pure
    # double-entry system this would live on the ledger; here it's
    # tracked separately for simplicity and reconciled into Equity
    # via Net Profit so the equation still balances.
    products = await db.products.find({}, {"cost_price": 1, "stock": 1}).to_list(None)
    inventory_value = sum((p.get("cost_price", 0) or 0) * (p.get("stock", 0) or 0) for p in products)

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
