"""Read-only reports.

Each endpoint is a single Mongo aggregation (or a small fixed batch),
deliberately avoiding the per-row queries that plagued the original
implementations. Date filters (`start_date`, `end_date`) are the
de-facto pagination — clients request what they care about.

This router holds the bulk of the operational reports
(outstanding, credit, sales, expenses, cash-bank, inventory, low-stock,
stock-movement, batch-traceability, production-yield,
supplier-payables, profit, profit-loss). The trial-balance and
balance-sheet reports live with the maintenance/financial router in
batch 7.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.database import db
from app.deps import get_current_user
from app.services.ledger import get_account_balance
from app.services.money import _money
from app.services.stock import get_all_product_stock

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports/outstanding")
async def report_outstanding(current_user: dict = Depends(get_current_user)):
    """Outstanding receivables — single aggregation instead of N+1."""
    customers = await db.customers.find({}, {"_id": 0}).to_list(None)
    if not customers:
        return {"report": [], "total": 0}

    customer_accounts = [f"customer:{c['id']}" for c in customers]
    pipeline = [
        {"$match": {"account": {"$in": customer_accounts}}},
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}},
        }},
    ]
    balance_map = {}
    async for row in db.ledger.aggregate(pipeline):
        cid = row["_id"].split(":", 1)[1]
        balance_map[cid] = row["balance"]

    report = []
    for customer in customers:
        outstanding = balance_map.get(customer["id"], 0)
        if outstanding > 0:
            report.append({
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "phone": customer.get("phone"),
                "outstanding": _money(outstanding),
            })

    report.sort(key=lambda x: x["outstanding"], reverse=True)
    total = _money(sum(r["outstanding"] for r in report))
    return {"report": report, "total": total}


@router.get("/reports/credit")
async def report_credit(current_user: dict = Depends(get_current_user)):
    """Customer available-credit report — single aggregation instead of N+1."""
    customers = await db.customers.find({}, {"_id": 0}).to_list(None)
    if not customers:
        return {"report": [], "total": 0}

    customer_ids = [c["id"] for c in customers]
    credit_pipeline = [
        {"$match": {"customer_id": {"$in": customer_ids}, "total": {"$gt": 0}}},
        {"$group": {"_id": "$customer_id", "credit": {"$sum": "$total"}}},
    ]
    credit_map = {}
    async for row in db.credit_notes.aggregate(credit_pipeline):
        credit_map[row["_id"]] = row["credit"]

    report = []
    for customer in customers:
        credit = credit_map.get(customer["id"], 0)
        if credit > 0:
            report.append({
                "customer_id": customer["id"],
                "customer_name": customer["name"],
                "phone": customer.get("phone"),
                "credit": _money(credit),
            })

    report.sort(key=lambda x: x["credit"], reverse=True)
    total = _money(sum(r["credit"] for r in report))
    return {"report": report, "total": total}


@router.get("/reports/sales")
async def report_sales(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"status": {"$ne": "draft"}}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date

    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    total = sum(inv["total"] for inv in invoices)
    collected = sum(inv.get("paid_amount", 0) for inv in invoices)
    total_cost = sum(inv.get("total_cost", 0) for inv in invoices)

    # Deduct credit notes in the same period
    cn_query = {}
    if start_date:
        cn_query["date"] = {"$gte": start_date}
    if end_date:
        cn_query.setdefault("date", {})["$lte"] = end_date
    credit_notes = await db.credit_notes.find(cn_query, {"_id": 0, "total": 1}).to_list(None)
    total_returns = sum(cn["total"] for cn in credit_notes)

    profit = (total - total_returns) - total_cost

    return {
        "invoices": invoices,
        "total_sales": total,
        "total_returns": total_returns,
        "net_sales": total - total_returns,
        "total_collected": collected,
        "pending": (total - total_returns) - collected,
        "total_cost": total_cost,
        "profit": profit
    }


@router.get("/reports/expenses")
async def report_expenses(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date

    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    total = sum(exp["amount"] for exp in expenses)

    by_category = {}
    for exp in expenses:
        cat = exp.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + exp["amount"]

    return {"expenses": expenses, "total": total, "by_category": by_category}


@router.get("/reports/cash-bank")
async def report_cash_bank(current_user: dict = Depends(get_current_user)):
    cash_balance = await get_account_balance("cash")
    bank_balance = await get_account_balance("bank")

    cash_entries = await db.ledger.find({"account": "cash"}, {"_id": 0}).sort("date", -1).to_list(50)
    bank_entries = await db.ledger.find({"account": "bank"}, {"_id": 0}).sort("date", -1).to_list(50)

    return {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_balance": cash_balance + bank_balance,
        "cash_transactions": cash_entries,
        "bank_transactions": bank_entries
    }


@router.get("/reports/inventory")
async def report_inventory(current_user: dict = Depends(get_current_user)):
    """Product stock report."""
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    stock_map = await get_all_product_stock()
    report = []
    total_value = 0

    for product in products:
        stock = stock_map.get(product["id"], 0)
        value = stock * product.get("cost_price", 0)
        report.append({
            "product_id": product["id"],
            "product_name": product["name"],
            "sku": product.get("sku"),
            "current_stock": stock,
            "cost_price": product.get("cost_price", 0),
            "selling_price": product.get("selling_price", 0),
            "value": value,
            "low_stock_threshold": product.get("low_stock_threshold", 10),
            "is_low_stock": stock < product.get("low_stock_threshold", 10)
        })
        total_value += value

    return {"report": report, "total_value": total_value}


@router.get("/reports/inventory-by-type")
async def report_inventory_by_type(current_user: dict = Depends(get_current_user)):
    """Inventory grouped by item type (Raw Material, WIP, Finished Good)."""
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    stock_map = await get_all_product_stock()
    summary = {}
    details = []
    total_value = 0

    for product in products:
        stock = stock_map.get(product["id"], 0)
        item_type = product.get("item_type", "FINISHED_GOOD")
        value = stock * product.get("cost_price", 0)

        detail = {
            "product_id": product["id"],
            "product_name": product["name"],
            "sku": product.get("sku"),
            "item_type": item_type,
            "current_stock": stock,
            "cost_price": product.get("cost_price", 0),
            "value": value
        }
        details.append(detail)

        if item_type not in summary:
            summary[item_type] = {"count": 0, "total_stock": 0, "total_value": 0}

        summary[item_type]["count"] += 1
        summary[item_type]["total_stock"] += stock
        summary[item_type]["total_value"] += value
        total_value += value

    return {"summary": summary, "details": details, "total_value": total_value}


@router.get("/reports/low-stock")
async def report_low_stock(current_user: dict = Depends(get_current_user)):
    """Low stock report."""
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    stock_map = await get_all_product_stock()
    report = []

    for product in products:
        stock = stock_map.get(product["id"], 0)
        threshold = product.get("low_stock_threshold", 10)
        if stock < threshold:
            report.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "sku": product.get("sku"),
                "current_stock": stock,
                "threshold": threshold,
                "shortage": threshold - stock
            })

    report.sort(key=lambda x: x["shortage"], reverse=True)
    return {"report": report, "count": len(report)}


@router.get("/reports/stock-movement")
async def report_stock_movement(product_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Stock movement report."""
    query = {}
    if product_id:
        query["product_id"] = product_id
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date

    movements = await db.stock_movements.find(query, {"_id": 0}).sort("date", -1).to_list(None)

    # Batch-fetch product names to avoid N+1 query
    product_ids = list({m["product_id"] for m in movements if m.get("product_id")})
    products_map = {}
    if product_ids:
        prods = await db.products.find({"id": {"$in": product_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(product_ids))
        products_map = {p["id"]: p["name"] for p in prods}
    for m in movements:
        m["product_name"] = products_map.get(m.get("product_id"), "Unknown")

    return {"movements": movements}


@router.get("/reports/batch-traceability")
async def report_batch_traceability(current_user: dict = Depends(get_current_user)):
    """Batch Traceability & Expiry Report."""
    products = await db.products.find(
        {"track_batches": True},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(None)
    if not products:
        return {"report": []}

    name_map = {p["id"]: p["name"] for p in products}
    # One query against batches instead of one per product. The `$in` filter
    # uses the existing (product_id, batch_number) compound index for lookup.
    batches = await db.batches.find(
        {"product_id": {"$in": list(name_map.keys())}, "current_stock": {"$gt": 0}},
        {"_id": 0},
    ).to_list(None)

    report = [{
        "product_id": b["product_id"],
        "product_name": name_map.get(b["product_id"], "Unknown"),
        "batch_number": b["batch_number"],
        "expiry_date": b.get("expiry_date"),
        "current_stock": b["current_stock"],
    } for b in batches]

    report.sort(key=lambda x: str(x.get("expiry_date") or "9999-12-31"))
    return {"report": report}


@router.get("/reports/production-yield")
async def report_production_yield(current_user: dict = Depends(get_current_user)):
    """Production Yield / COGS Report.

    Status values are stored UPPERCASE ("COMPLETED"), but the previous
    query used lowercase "completed", so the report always returned empty.
    Field names also corrected to match the production-order schema
    actually written by `complete_production_order` (product_id, quantity,
    completed_at, ingredients[].material_id, ingredients[].quantity_consumed
    / quantity_required).
    """
    orders = await db.production_orders.find({"status": "COMPLETED"}, {"_id": 0}).sort("completed_at", -1).to_list(100)
    if not orders:
        return {"report": []}

    # Batch-fetch every product (finished good + raw material) referenced by
    # any order in one query — was previously a deep N+1 (one query per order
    # plus one per ingredient, ~600 queries for 100 orders × 5 ingredients).
    needed_ids: set[str] = set()
    for order in orders:
        if order.get("product_id"):
            needed_ids.add(order["product_id"])
        for ing in order.get("ingredients", []):
            if ing.get("material_id"):
                needed_ids.add(ing["material_id"])

    product_map = {}
    if needed_ids:
        async for p in db.products.find(
            {"id": {"$in": list(needed_ids)}},
            {"_id": 0, "id": 1, "name": 1, "cost_price": 1},
        ):
            product_map[p["id"]] = p

    report = []
    for order in orders:
        product = product_map.get(order.get("product_id"))
        if not product:
            continue
        qty = order.get("quantity", 0)
        fg_value = _money(qty * product.get("cost_price", 0))
        raw_material_cost = 0.0
        for ing in order.get("ingredients", []):
            consumed = ing.get("quantity_consumed") or ing.get("quantity_required", 0)
            mat = product_map.get(ing.get("material_id"))
            unit_cost = mat.get("cost_price", 0) if mat else 0
            raw_material_cost += _money(consumed * unit_cost)
        raw_material_cost = _money(raw_material_cost)
        report.append({
            "order_number": order["order_number"],
            "product_name": product["name"],
            "completed_at": order.get("completed_at"),
            "qty_produced": qty,
            "materials_cost": raw_material_cost,
            "fg_value": fg_value,
            "yield_variance": _money(fg_value - raw_material_cost),
        })
    return {"report": report}


@router.get("/reports/supplier-payables")
async def report_supplier_payables(current_user: dict = Depends(get_current_user)):
    """Supplier payables report."""
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(None)

    # Batch-compute supplier balances via aggregation (avoid N+1 per-supplier ledger calls)
    balance_pipeline = [
        {"$match": {"account": {"$regex": "^supplier:"}}},
        {"$group": {"_id": "$account", "total_debit": {"$sum": "$debit"}, "total_credit": {"$sum": "$credit"}}}
    ]
    balance_results = await db.ledger.aggregate(balance_pipeline).to_list(None)
    balance_map = {r["_id"]: r["total_debit"] - r["total_credit"] for r in balance_results}

    report = []
    for supplier in suppliers:
        account_key = f"supplier:{supplier['id']}"
        balance = balance_map.get(account_key, 0.0)
        payable = max(0, -balance)
        if payable > 0:
            report.append({
                "supplier_id": supplier["id"],
                "supplier_name": supplier["name"],
                "phone": supplier.get("phone"),
                "payable": payable
            })

    report.sort(key=lambda x: x["payable"], reverse=True)
    total = sum(r["payable"] for r in report)

    return {"report": report, "total": total}


@router.get("/reports/profit")
async def report_profit(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Profit report."""
    query = {"status": {"$ne": "draft"}}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date

    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(None)

    total_sales = sum(inv["total"] for inv in invoices)
    total_cost = sum(inv.get("total_cost", 0) for inv in invoices)
    gross_profit = total_sales - total_cost

    exp_query = {}
    if start_date:
        exp_query["date"] = {"$gte": start_date}
    if end_date:
        exp_query.setdefault("date", {})["$lte"] = end_date

    expenses = await db.expenses.find(exp_query, {"_id": 0}).sort("date", -1).to_list(None)
    total_expenses = sum(exp["amount"] for exp in expenses)

    net_profit = gross_profit - total_expenses

    return {
        "total_sales": total_sales,
        "total_cost": total_cost,
        "gross_profit": gross_profit,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "invoice_count": len(invoices),
        "margin_percent": (gross_profit / total_sales * 100) if total_sales > 0 else 0
    }


@router.get("/reports/profit-loss")
async def report_profit_loss(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Detailed Profit & Loss statement with category breakdown."""
    date_filter = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date

    inv_query = {"status": {"$ne": "draft"}}
    exp_query = {}
    cn_query = {}
    dn_query = {}
    if date_filter:
        inv_query["date"] = date_filter
        exp_query["date"] = date_filter
        cn_query["date"] = date_filter
        dn_query["date"] = date_filter

    invoices = await db.invoices.find(inv_query, {"_id": 0}).sort("date", -1).to_list(None)
    total_sales = sum(inv["total"] for inv in invoices)
    total_cost_of_goods = sum(inv.get("total_cost", 0) for inv in invoices)

    # Returns: credit notes (reduce income) & debit notes (reduce purchases cost)
    credit_notes = await db.credit_notes.find(cn_query, {"_id": 0}).sort("date", -1).to_list(None)
    total_credit_notes = sum(cn["total"] for cn in credit_notes)

    debit_notes = await db.debit_notes.find(dn_query, {"_id": 0}).sort("date", -1).to_list(None)
    total_debit_notes = sum(dn["total"] for dn in debit_notes)

    net_sales = total_sales - total_credit_notes
    net_cost = total_cost_of_goods - total_debit_notes
    gross_profit = net_sales - net_cost

    expenses = await db.expenses.find(exp_query, {"_id": 0}).sort("date", -1).to_list(None)
    expense_categories = {}
    for exp in expenses:
        cat = exp.get("category", "Other") or "Other"
        expense_categories[cat] = expense_categories.get(cat, 0) + exp["amount"]

    total_expenses = sum(expense_categories.values())
    net_profit = gross_profit - total_expenses

    return {
        "income": {
            "total_sales": total_sales,
            "credit_notes": total_credit_notes,
            "net_sales": net_sales,
            "invoice_count": len(invoices)
        },
        "cost_of_goods": {
            "total_cost": total_cost_of_goods,
            "debit_notes": total_debit_notes,
            "net_cost": net_cost
        },
        "gross_profit": gross_profit,
        "expenses": {
            "categories": expense_categories,
            "total": total_expenses
        },
        "net_profit": net_profit,
        "margin_percent": (gross_profit / net_sales * 100) if net_sales > 0 else 0
    }
