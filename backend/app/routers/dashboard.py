"""Dashboard summary endpoint.

Every read this endpoint needs is independent of the others (no result
feeds into another), so they all run in parallel via asyncio.gather.
On the live stack this drops the dashboard from ~17 sequential round-
trips to a single concurrent batch, which dominates latency on the
most-called page of the app.

The N+1 collapse from prior iterations (single stock-map aggregation,
single outstanding/payable aggregations) is what makes this safe to
gather — no per-row queries inside the parallel section.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.database import db
from app.deps import get_current_user
from app.services.ledger import get_account_balance
from app.services.stock import get_all_product_stock

router = APIRouter(prefix="/api", tags=["dashboard"])


async def _sum_positive_account_balances(prefix: str) -> float:
    """Sum (debit - credit) per account where name starts with `prefix`,
    then sum only the positive balances. Used for outstanding receivables."""
    pipeline = [
        {"$match": {"account": {"$regex": f"^{prefix}"}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    total = 0.0
    async for row in db.ledger.aggregate(pipeline):
        total += max(0, row["balance"])
    return round(total, 2)


async def _sum_negative_account_balances(prefix: str) -> float:
    """Sum (credit - debit) per account where name starts with `prefix`,
    then sum only the positive results. Used for supplier payables — a
    credit balance means we owe them."""
    pipeline = [
        {"$match": {"account": {"$regex": f"^{prefix}"}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    total = 0.0
    async for row in db.ledger.aggregate(pipeline):
        total += max(0, -row["balance"])
    return round(total, 2)


async def _aggregate_total(coll, pipeline) -> float:
    """Run a $group {total: $sum: ...} pipeline and return the scalar."""
    res = await coll.aggregate(pipeline).to_list(1)
    return round(res[0]["total"], 2) if res else 0.0


@router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_start = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")

    today_sales_pipeline = [
        {"$match": {"date": today, "status": {"$ne": "draft"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    month_sales_pipeline = [
        {"$match": {"date": {"$gte": month_start}, "status": {"$ne": "draft"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    credit_pipeline = [
        {"$match": {"total": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    month_exp_pipeline = [
        {"$match": {"date": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]

    (
        cash_balance,
        bank_balance,
        total_outstanding,
        total_credit,
        total_payable,
        today_sales,
        monthly_sales,
        monthly_expenses,
        products,
        stock_map,
        recent_invoices,
        recent_payments,
        recent_purchases,
        recent_expenses,
        overdue_count,
        total_customers,
        total_suppliers,
        active_work_orders,
        planned_work_orders,
        completed_work_orders,
    ) = await asyncio.gather(
        get_account_balance("cash"),
        get_account_balance("bank"),
        _sum_positive_account_balances("customer:"),
        _aggregate_total(db.credit_notes, credit_pipeline),
        _sum_negative_account_balances("supplier:"),
        _aggregate_total(db.invoices, today_sales_pipeline),
        _aggregate_total(db.invoices, month_sales_pipeline),
        _aggregate_total(db.expenses, month_exp_pipeline),
        db.products.find({}, {"_id": 0}).to_list(None),
        get_all_product_stock(),
        db.invoices.find({}, {"_id": 0}).sort("date", -1).to_list(5),
        db.payments.find({}, {"_id": 0}).sort("date", -1).to_list(5),
        db.purchases.find({}, {"_id": 0}).sort("date", -1).to_list(5),
        db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(5),
        db.invoices.count_documents({"status": {"$in": ["unpaid", "partially_paid"]}, "date": {"$lt": today}}),
        db.customers.count_documents({}),
        db.suppliers.count_documents({}),
        # Production status counts — values are stored UPPERCASE
        # ("IN_PROGRESS", "PLANNED", "COMPLETED"); the previous code matched
        # lowercase and always returned zero. completed_work_orders used to
        # filter on `end_date` but the field is `completed_at`.
        db.production_orders.count_documents({"status": "IN_PROGRESS"}),
        db.production_orders.count_documents({"status": "PLANNED"}),
        db.production_orders.count_documents({"status": "COMPLETED", "completed_at": {"$gte": month_start}}),
    )

    # Low-stock list — derived in Python from the products list and the
    # stock_map computed above.
    low_stock_count = 0
    low_stock_products = []
    for p in products:
        stock = stock_map.get(p["id"], 0)
        threshold = p.get("low_stock_threshold", 10)
        if stock < threshold:
            low_stock_count += 1
            if len(low_stock_products) < 5:
                low_stock_products.append({
                    "id": p["id"],
                    "name": p["name"],
                    "current_stock": stock,
                    "low_stock_threshold": threshold,
                })
    total_products = len(products)

    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_outstanding": total_outstanding,
        "total_credit": total_credit,
        "total_payable": total_payable,
        "today_sales": today_sales,
        "monthly_sales": monthly_sales,
        "monthly_expenses": monthly_expenses,
        "low_stock_count": low_stock_count,
        "low_stock_products": low_stock_products,
        "overdue_count": overdue_count,
        "total_customers": total_customers,
        "total_suppliers": total_suppliers,
        "total_products": total_products,
        "recent_invoices": recent_invoices,
        "recent_payments": recent_payments,
        "recent_purchases": recent_purchases,
        "recent_expenses": recent_expenses,
        "active_work_orders": active_work_orders,
        "planned_work_orders": planned_work_orders,
        "completed_work_orders": completed_work_orders,
    }
