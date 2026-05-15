"""Dashboard summary endpoint.

The previous implementation fired ~2N+M+K+5 sequential aggregations
(N customers, M suppliers, K products) and was the main cause of the
"customers fail to load" timeouts. This version uses a fixed set of
aggregations regardless of data size — robust to 5–10K invoices/year
and tens of thousands of ledger entries.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.database import db
from app.deps import get_current_user
from app.services.ledger import get_account_balance
from app.services.stock import get_all_product_stock

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_start = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")

    cash_balance = await get_account_balance("cash")
    bank_balance = await get_account_balance("bank")

    # Customer outstanding (only positive) + supplier payable (only positive)
    # done in one aggregation each by grouping ledger entries whose account
    # starts with the relevant prefix.
    cust_outstanding_pipeline = [
        {"$match": {"account": {"$regex": "^customer:"}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    total_outstanding = 0.0
    async for row in db.ledger.aggregate(cust_outstanding_pipeline):
        total_outstanding += max(0, row["balance"])
    total_outstanding = round(total_outstanding, 2)

    # Total available credit across all customers — single aggregation
    credit_pipeline = [
        {"$match": {"total": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    credit_result = await db.credit_notes.aggregate(credit_pipeline).to_list(1)
    total_credit = round(credit_result[0]["total"], 2) if credit_result else 0.0

    sup_payable_pipeline = [
        {"$match": {"account": {"$regex": "^supplier:"}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    total_payable = 0.0
    async for row in db.ledger.aggregate(sup_payable_pipeline):
        # Supplier balance is negative when we owe them (credit side)
        total_payable += max(0, -row["balance"])
    total_payable = round(total_payable, 2)

    today_sales_pipeline = [
        {"$match": {"date": today, "status": {"$ne": "draft"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    today_sales_res = await db.invoices.aggregate(today_sales_pipeline).to_list(1)
    today_sales = round(today_sales_res[0]["total"], 2) if today_sales_res else 0.0

    month_sales_pipeline = [
        {"$match": {"date": {"$gte": month_start}, "status": {"$ne": "draft"}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}},
    ]
    month_sales_res = await db.invoices.aggregate(month_sales_pipeline).to_list(1)
    monthly_sales = round(month_sales_res[0]["total"], 2) if month_sales_res else 0.0

    # Low-stock detection: stock per product in one aggregation via the
    # shared service helper, then join in Python against the products list
    # to apply per-product thresholds and produce the top-5 list.
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    stock_map = await get_all_product_stock()

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

    recent_invoices = await db.invoices.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_payments = await db.payments.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_purchases = await db.purchases.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(5)

    overdue_count = await db.invoices.count_documents(
        {"status": {"$in": ["unpaid", "partially_paid"]}, "date": {"$lt": today}}
    )

    month_exp_pipeline = [
        {"$match": {"date": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    month_exp_res = await db.expenses.aggregate(month_exp_pipeline).to_list(1)
    monthly_expenses = round(month_exp_res[0]["total"], 2) if month_exp_res else 0.0

    total_customers = await db.customers.count_documents({})
    total_suppliers = await db.suppliers.count_documents({})
    total_products = len(products)

    # Production status counts — values are stored UPPERCASE
    # ("IN_PROGRESS", "PLANNED", "COMPLETED"); the previous code matched
    # lowercase and always returned zero. Also "completed_work_orders" used
    # to filter on `end_date` but the field is `completed_at`.
    active_work_orders = await db.production_orders.count_documents({"status": "IN_PROGRESS"})
    planned_work_orders = await db.production_orders.count_documents({"status": "PLANNED"})
    completed_work_orders = await db.production_orders.count_documents(
        {"status": "COMPLETED", "completed_at": {"$gte": month_start}}
    )

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
        "completed_work_orders": completed_work_orders
    }
