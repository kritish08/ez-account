import os
import sys
import shutil
import uuid
import json
import base64
import secrets
import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, APIRouter, Header, Query, Request, status, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING, ReturnDocument
from jose import jwt, JWTError
import bcrypt
import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fido2.server import Fido2Server
from fido2.webauthn import PublicKeyCredentialRpEntity
from fido2 import cbor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from dotenv import load_dotenv

# ============================================================
# Phase 0 of the server.py refactor — see docs/refactor-plan.md.
# Config, database client, and Pydantic models have moved into the
# `app/` package. They're re-exported here so the (still very long)
# route handlers below can keep referencing the same symbols.
# ============================================================
from app.config import (
    MONGO_URL, DB_NAME, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    MASTER_ENCRYPTION_KEY, WEBAUTHN_RP_ID, WEBAUTHN_RP_NAME,
)
from app.database import client, db
from app.deps import security, get_current_user

# ============================================================
# Phase 1 — helpers extracted to app/services/.  Imported below so the
# (still-very-long) route handlers in this file keep working unchanged.
# ============================================================
from app.services.auth import verify_password, get_password_hash, create_access_token
from app.services.crypto import encrypt_data, decrypt_data
from app.services.money import _money
from app.services.counters import (
    _next_seq,
    get_next_invoice_number, get_next_purchase_number,
    get_next_credit_note_number, get_next_debit_note_number,
)
from app.services.ledger import (
    create_ledger_entry, delete_ledger_entries, get_account_balance,
)
from app.services.stock import (
    get_product_stock, create_stock_movement, delete_stock_movements,
)
from app.services.payments_apply import (
    apply_payment_fifo, get_customer_credit, apply_debit_to_purchase,
    apply_credit_to_invoice, apply_credit_note_to_invoice,
    apply_advance_payment_to_invoice,
)
from app.services.passkey import fido_server, _b64url_to_bytes, _rebuild_attested_credentials
from app.services.backup import scheduler, scheduled_backup_job, apply_backup_schedule

# ============================================================
# Phase 2 — route handlers extracted to app/routers/.  Wired in below via
# app.include_router. Phase 2 will move the remaining inline handlers
# (still in this file) over batch by batch.
# ============================================================
from app.routers.health import router as health_router
from app.routers.auth import router as auth_router
from app.routers.business import router as business_router
from app.routers.products import router as products_router
from app.routers.customers import router as customers_router
from app.routers.suppliers import router as suppliers_router
from app.routers.bom import router as bom_router
from app.routers.production import router as production_router
from app.routers.purchases import router as purchases_router
from app.routers.invoices import router as invoices_router
from app.routers.payments import router as payments_router
from app.routers.credit_notes import router as credit_notes_router
from app.routers.debit_notes import router as debit_notes_router


# Internal imports
from services.ai_service import parse_invoice_image

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Voice assistant session manager — instantiated inside lifespan because its
# __init__ schedules a background task and needs a running event loop.
from services.websocket_session_manager import WebSocketSessionManager
ws_session_manager: Optional[WebSocketSessionManager] = None

async def _safe_create_index(coll_name: str, keys, **kwargs):
    """Create a Mongo index, logging (not raising) on failure so one bad
    index doesn't prevent the rest from being created."""
    try:
        await db[coll_name].create_index(keys, **kwargs)
    except Exception as e:
        logger.warning(f"Index create failed on {coll_name} {keys}: {e}")


async def _seed_counter_from_max(counter_name: str, coll_name: str, field: str, prefix: str):
    """One-time seed of the atomic counter from existing max value in the
    collection. Uses $max so it is idempotent and safe to call on every boot."""
    try:
        last = await db[coll_name].find_one(
            {field: {"$regex": f"^{prefix}"}},
            {"_id": 0, field: 1},
            sort=[(field, -1)],
        )
        if not last:
            return
        try:
            max_seq = int(last[field].replace(prefix, ""))
        except (ValueError, KeyError, TypeError):
            return
        await db.counters.update_one(
            {"_id": counter_name},
            {"$max": {"seq": max_seq}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Counter seed failed for {counter_name}: {e}")




# Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting up...")
    global ws_session_manager
    ws_session_manager = WebSocketSessionManager(db)

    # ---- Indexes ----
    # Hot-path lookups by `id` and `email`. Without these every authenticated
    # request scanned the whole users/customers/suppliers/products collection.
    await _safe_create_index("users", "id")
    await _safe_create_index("users", "email", unique=True,
                             partialFilterExpression={"email": {"$exists": True}})
    await _safe_create_index("customers", "id")
    await _safe_create_index("suppliers", "id")
    await _safe_create_index("products", "id")
    await _safe_create_index("invoices", "id")
    await _safe_create_index("purchases", "id")
    await _safe_create_index("payments", "id")
    await _safe_create_index("payments", "customer_id")
    await _safe_create_index("credit_notes", "id")
    await _safe_create_index("credit_notes", "customer_id")
    await _safe_create_index("debit_notes", "id")
    await _safe_create_index("debit_notes", "supplier_id")
    await _safe_create_index("expenses", "id")
    await _safe_create_index("production_orders", "id")
    await _safe_create_index("bill_of_materials", "product_id")
    await _safe_create_index("advance_payments", "id")
    await _safe_create_index("advance_payments", "customer_id")
    await _safe_create_index("payment_allocations", "invoice_id")
    await _safe_create_index("payment_allocations", "payment_id")

    # Existing compound indexes
    await _safe_create_index("ledger", [("account", ASCENDING), ("date", DESCENDING)])
    await _safe_create_index("ledger", [("ref_type", ASCENDING), ("ref_id", ASCENDING)])
    await _safe_create_index("stock_movements", [("product_id", ASCENDING), ("date", DESCENDING)])
    await _safe_create_index("stock_movements", [("ref_type", ASCENDING), ("ref_id", ASCENDING)])
    await _safe_create_index("invoices", [("customer_id", ASCENDING), ("status", ASCENDING), ("date", DESCENDING)])
    await _safe_create_index("production_orders", [("status", ASCENDING), ("product_id", ASCENDING)])

    # Unique reference-number indexes (with partial filter so legacy docs
    # missing the field don't break index creation).
    await _safe_create_index("invoices", "invoice_number", unique=True,
                             partialFilterExpression={"invoice_number": {"$exists": True}})
    await _safe_create_index("purchases", "purchase_number", unique=True,
                             partialFilterExpression={"purchase_number": {"$exists": True}})
    await _safe_create_index("credit_notes", "credit_note_number", unique=True,
                             partialFilterExpression={"credit_note_number": {"$exists": True}})
    await _safe_create_index("debit_notes", "debit_note_number", unique=True,
                             partialFilterExpression={"debit_note_number": {"$exists": True}})
    await _safe_create_index("production_orders", "order_number", unique=True,
                             partialFilterExpression={"order_number": {"$exists": True}})

    # Serial/batch uniqueness per product
    await _safe_create_index("serial_numbers",
                             [("product_id", ASCENDING), ("serial_number", ASCENDING)],
                             unique=True,
                             partialFilterExpression={"serial_number": {"$exists": True}})
    await _safe_create_index("batches",
                             [("product_id", ASCENDING), ("batch_number", ASCENDING)],
                             unique=True,
                             partialFilterExpression={"batch_number": {"$exists": True}})

    # Counter doc primary key (Mongo gives _id a unique index automatically,
    # but make the intent explicit and create the collection eagerly).
    await _safe_create_index("counters", "_id")

    # WebAuthn challenge state — TTL index on expires_at cleans up stale
    # registration/auth handshakes (5-min window) so abandoned flows don't
    # accumulate. Also index the lookup keys.
    await _safe_create_index("webauthn_states", "expires_at", expireAfterSeconds=0)
    await _safe_create_index("webauthn_states", [("user_id", ASCENDING), ("type", ASCENDING)])
    await _safe_create_index("webauthn_states", [("email", ASCENDING), ("type", ASCENDING)])
    # Unique passkey credential id (per user, but credential ids are
    # globally unique per the WebAuthn spec, so a plain unique index is fine).
    await _safe_create_index("users", "passkeys.id",
                             partialFilterExpression={"passkeys.id": {"$exists": True}})

    # Seed atomic counters from the existing highest reference numbers so
    # the new generator picks up where the old (racey) generator left off.
    await _seed_counter_from_max("invoice", "invoices", "invoice_number", "INV-")
    await _seed_counter_from_max("purchase", "purchases", "purchase_number", "PUR-")
    await _seed_counter_from_max("credit_note", "credit_notes", "credit_note_number", "CN-")
    await _seed_counter_from_max("debit_note", "debit_notes", "debit_note_number", "DN-")
    await _seed_counter_from_max("production_order", "production_orders", "order_number", "WO-")

    # One-time migration: backfill `id` on BOMs created before the stable-id
    # fix. Without an id, production-order `bom_id` is always null because
    # the order copies it via `bom["id"] if bom and "id" in bom else None`.
    try:
        missing_id_count = await db.bill_of_materials.count_documents({"id": {"$exists": False}})
        if missing_id_count:
            async for bom in db.bill_of_materials.find({"id": {"$exists": False}}, {"_id": 1}):
                await db.bill_of_materials.update_one(
                    {"_id": bom["_id"]},
                    {"$set": {"id": str(uuid.uuid4())}},
                )
            logger.info(f"Backfilled `id` on {missing_id_count} legacy BOM docs.")
    except Exception as e:
        logger.warning(f"BOM id backfill skipped: {e}")

    logger.info("MongoDB indexes & counters initialised.")

    # Start the cron scheduler and apply any saved backup schedule.
    try:
        scheduler.start()
        logger.info("Background scheduler started.")
        sched_config = await db.settings.find_one({"type": "backup_schedule"}, {"_id": 0})
        if sched_config and sched_config.get("enabled"):
            apply_backup_schedule(sched_config)
    except Exception as e:
        logger.warning(f"Could not start scheduler / load backup schedule: {e}")

    yield
    logger.info("Server shutting down...")
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()

app = FastAPI(title="EZ Accounts by Kyrex API", version="2.0.0", lifespan=lifespan)

# CORS is registered later (near app.include_router) so it can use the
# CORS_ORIGINS env var. Do not add a duplicate wildcard registration here —
# browsers reject `Access-Control-Allow-Origin: *` with `allow_credentials=True`.

# Auth Scheme
security = HTTPBearer()

# Static Files
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

api_router = APIRouter(prefix="/api")

# ============================================================
# Phase 0 — Pydantic models extracted to app/schemas/.  Imported below so
# the (still very long) route handlers in this file keep referencing the
# same symbols. Phase 2 will move the route handlers themselves into
# app/routers/*.
# ============================================================
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.settings import (
    ModulesSettings, BackupScheduleSettings, S3Settings,
    SystemSettings, SystemResetRequest,
)



# ============== AUTH + PASSKEY + BUSINESS ROUTES ==============
# Moved to app/routers/{auth,business}.py — see Phase 2 import block above.


# ============== PRODUCTS + SUPPLIERS + CUSTOMERS ROUTES ==============
# Moved to app/routers/{products,suppliers,customers}.py — see Phase 2 imports.

# ============== BOM + PRODUCTION ROUTES ==============
# Moved to app/routers/{bom,production}.py — see Phase 2 imports.

# ============== PURCHASES + INVOICES ROUTES ==============
# Moved to app/routers/{purchases,invoices}.py — see Phase 2 imports.

# ============== PAYMENTS + CN + DN ROUTES ==============
# Moved to app/routers/{payments,credit_notes,debit_notes}.py — see Phase 2 imports.

# ============== EXPENSES ==============

@api_router.post("/expenses")
async def create_expense(expense: ExpenseCreate, current_user: dict = Depends(get_current_user)):
    expense_id = str(uuid.uuid4())
    expense_date = expense.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    expense_doc = {
        "id": expense_id,
        **expense.model_dump(),
        "date": expense_date,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.expenses.insert_one(expense_doc)
    
    await create_ledger_entry(
        account=expense.mode,
        debit=0,
        credit=expense.amount,
        narration=f"Expense: {expense.description}",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )

    # Debit Expense Account
    await create_ledger_entry(
        account=f"expense:{expense.category}",
        debit=expense.amount,
        credit=0,
        narration=f"Expense: {expense.description}",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )
    
    return {"message": "Expense recorded", "id": expense_id}

@api_router.get("/expenses")
async def list_expenses(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    return expenses

@api_router.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, expense: ExpenseUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.expenses.find_one({"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
        
    # Reverse Ledger
    await delete_ledger_entries("expense", expense_id)
    
    # Update Doc
    update_data = expense.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.expenses.update_one({"id": expense_id}, {"$set": update_data})
    
    # Re-create Ledger
    expense_date = expense.date or existing["date"]
    await create_ledger_entry(
        account=expense.mode,
        debit=0,
        credit=expense.amount,
        narration=f"Expense: {expense.description} (updated)",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )

    # Debit Expense Account (New)
    await create_ledger_entry(
        account=f"expense:{expense.category}",
        debit=expense.amount,
        credit=0,
        narration=f"Expense: {expense.description} (updated)",
        ref_type="expense",
        ref_id=expense_id,
        date=expense_date
    )
    
    return {"message": "Expense updated"}

@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    existing = await db.expenses.find_one({"id": expense_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Expense not found")
        
    await delete_ledger_entries("expense", expense_id)
    await db.expenses.delete_one({"id": expense_id})
    return {"message": "Expense deleted"}

# ============== DASHBOARD ==============

@api_router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    """Dashboard summary.

    Previously this fired 2N+M+K+5 sequential aggregations (N customers,
    M suppliers, K products, plus per-status counts). Rewritten as a
    fixed-cost set of aggregations regardless of data size — robust to
    5-10K invoices/year and tens of thousands of ledger entries.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month_start = datetime.now(timezone.utc).replace(day=1).strftime("%Y-%m-%d")

    # Cash / bank balances — two aggregations
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

    # Sales totals — single aggregation each
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

    # Low-stock detection: compute stock per product in one aggregation,
    # then join in Python against the products list to apply per-product
    # thresholds and produce the top-5 list.
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    stock_pipeline = [
        {"$group": {
            "_id": "$product_id",
            "stock": {"$sum": {"$subtract": ["$quantity_in", "$quantity_out"]}},
        }},
    ]
    stock_map = {}
    async for row in db.stock_movements.aggregate(stock_pipeline):
        stock_map[row["_id"]] = row["stock"]

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

    # Recent activity (already capped at 5)
    recent_invoices = await db.invoices.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_payments = await db.payments.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_purchases = await db.purchases.find({}, {"_id": 0}).sort("date", -1).to_list(5)
    recent_expenses = await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(5)

    # Overdue invoices — count via count_documents (no need to load the docs)
    overdue_count = await db.invoices.count_documents(
        {"status": {"$in": ["unpaid", "partially_paid"]}, "date": {"$lt": today}}
    )

    # Monthly expenses — single aggregation
    month_exp_pipeline = [
        {"$match": {"date": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]
    month_exp_res = await db.expenses.aggregate(month_exp_pipeline).to_list(1)
    monthly_expenses = round(month_exp_res[0]["total"], 2) if month_exp_res else 0.0

    # Entity counts
    total_customers = await db.customers.count_documents({})
    total_suppliers = await db.suppliers.count_documents({})
    total_products = len(products)

    # Production status counts — the previous code used lowercase status
    # values ("in_progress", "planned", "completed") but the actual stored
    # values are UPPERCASE ("IN_PROGRESS", "PLANNED", "COMPLETED"), so all
    # three counts were always zero. Also fixed: "completed_work_orders"
    # was filtering on `end_date` but the field is `completed_at`.
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

# ============== REPORTS ==============

@api_router.get("/reports/outstanding")
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

@api_router.get("/reports/credit")
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

@api_router.get("/reports/sales")
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

@api_router.get("/reports/expenses")
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

@api_router.get("/reports/cash-bank")
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

@api_router.get("/reports/inventory")
async def report_inventory(current_user: dict = Depends(get_current_user)):
    """Product stock report"""
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    report = []
    total_value = 0
    
    for product in products:
        stock = await get_product_stock(product["id"])
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

@api_router.get("/reports/inventory-by-type")
async def report_inventory_by_type(current_user: dict = Depends(get_current_user)):
    """Inventory grouped by item type (Raw Material, WIP, Finished Good)"""
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    summary = {}
    details = []
    total_value = 0
    
    for product in products:
        stock = await get_product_stock(product["id"])
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


@api_router.get("/reports/low-stock")
async def report_low_stock(current_user: dict = Depends(get_current_user)):
    """Low stock report"""
    products = await db.products.find({}, {"_id": 0}).to_list(None)
    report = []
    
    for product in products:
        stock = await get_product_stock(product["id"])
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

@api_router.get("/reports/stock-movement")
async def report_stock_movement(product_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Stock movement report"""
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

@api_router.get("/reports/batch-traceability")
async def report_batch_traceability(current_user: dict = Depends(get_current_user)):
    """Batch Traceability & Expiry Report"""
    products = await db.products.find({"track_batches": True}, {"_id": 0}).to_list(None)
    report = []
    for product in products:
        batches = await db.batches.find({"product_id": product["id"], "current_stock": {"$gt": 0}}, {"_id": 0}).to_list(100)
        for b in batches:
            report.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "batch_number": b["batch_number"],
                "expiry_date": b.get("expiry_date"),
                "current_stock": b["current_stock"]
            })
    report.sort(key=lambda x: str(x.get("expiry_date") or "9999-12-31"))
    return {"report": report}

@api_router.get("/reports/production-yield")
async def report_production_yield(current_user: dict = Depends(get_current_user)):
    """Production Yield / COGS Report.

    Status values are stored UPPERCASE ("COMPLETED"), but this query used
    lowercase "completed", so the report always returned empty.
    Field names also corrected to match the production-order schema actually
    written by `complete_production_order` (product_id, quantity, completed_at,
    ingredients[].material_id, ingredients[].quantity_consumed/quantity_required).
    """
    orders = await db.production_orders.find({"status": "COMPLETED"}, {"_id": 0}).sort("completed_at", -1).to_list(100)
    report = []
    for order in orders:
        product = await db.products.find_one({"id": order.get("product_id")}, {"_id": 0, "name": 1, "cost_price": 1})
        if not product:
            continue
        qty = order.get("quantity", 0)
        fg_value = _money(qty * product.get("cost_price", 0))
        raw_material_cost = 0.0
        for ing in order.get("ingredients", []):
            consumed = ing.get("quantity_consumed") or ing.get("quantity_required", 0)
            mat = await db.products.find_one({"id": ing.get("material_id")}, {"_id": 0, "cost_price": 1})
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

@api_router.get("/reports/supplier-payables")
async def report_supplier_payables(current_user: dict = Depends(get_current_user)):
    """Supplier payables report"""
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

@api_router.get("/reports/profit")
async def report_profit(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Profit report"""
    query = {"status": {"$ne": "draft"}}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    invoices = await db.invoices.find(query, {"_id": 0}).sort("date", -1).to_list(None)
    
    total_sales = sum(inv["total"] for inv in invoices)
    total_cost = sum(inv.get("total_cost", 0) for inv in invoices)
    gross_profit = total_sales - total_cost
    
    # Get expenses in same period
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

@api_router.get("/reports/profit-loss")
async def report_profit_loss(start_date: Optional[str] = None, end_date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Detailed Profit & Loss statement with category breakdown"""
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
    
    # Income: invoices
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
    
    # Expenses grouped by category
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

# ============== EXPORT ENDPOINTS ==============

def create_csv_response(data: list, filename: str, fieldnames: list) -> StreamingResponse:
    """Create CSV file response"""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

def create_excel_response(data: list, filename: str, headers: list) -> StreamingResponse:
    """Create Excel file response"""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    
    for row in data:
        ws.append([row.get(h.lower().replace(" ", "_"), row.get(h, "")) for h in headers])
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api_router.get("/export/outstanding")
async def export_outstanding(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_outstanding(current_user)
    data = report["report"]
    
    if format == "excel":
        return create_excel_response(data, "outstanding_report.xlsx", ["customer_name", "phone", "outstanding"])
    return create_csv_response(data, "outstanding_report.csv", ["customer_name", "phone", "outstanding"])

@api_router.get("/export/credit")
async def export_credit(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_credit(current_user)
    data = report["report"]
    
    if format == "excel":
        return create_excel_response(data, "credit_report.xlsx", ["customer_name", "phone", "credit"])
    return create_csv_response(data, "credit_report.csv", ["customer_name", "phone", "credit"])

@api_router.get("/export/sales")
async def export_sales(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_sales(start_date, end_date, current_user)
    data = [{
        "invoice_number": inv["invoice_number"],
        "customer_name": inv["customer_name"],
        "date": inv["date"],
        "total": inv["total"],
        "paid_amount": inv.get("paid_amount", 0),
        "status": inv["status"]
    } for inv in report["invoices"]]
    
    if format == "excel":
        return create_excel_response(data, "sales_report.xlsx", ["invoice_number", "customer_name", "date", "total", "paid_amount", "status"])
    return create_csv_response(data, "sales_report.csv", ["invoice_number", "customer_name", "date", "total", "paid_amount", "status"])

@api_router.get("/export/expenses")
async def export_expenses(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_expenses(start_date, end_date, current_user)
    data = report["expenses"]
    
    if format == "excel":
        return create_excel_response(data, "expenses_report.xlsx", ["description", "category", "date", "amount", "mode"])
    return create_csv_response(data, "expenses_report.csv", ["description", "category", "date", "amount", "mode"])

@api_router.get("/export/inventory")
async def export_inventory(format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_inventory(current_user)
    data = report["report"]
    
    if format == "excel":
        return create_excel_response(data, "inventory_report.xlsx", ["product_name", "sku", "current_stock", "cost_price", "selling_price", "value"])
    return create_csv_response(data, "inventory_report.csv", ["product_name", "sku", "current_stock", "cost_price", "selling_price", "value"])

@api_router.get("/export/profit")
async def export_profit(start_date: Optional[str] = None, end_date: Optional[str] = None, format: str = "csv", current_user: dict = Depends(get_current_user)):
    report = await report_profit(start_date, end_date, current_user)
    data = [{
        "metric": "Total Sales",
        "value": report["total_sales"]
    }, {
        "metric": "Cost of Goods",
        "value": report["total_cost"]
    }, {
        "metric": "Gross Profit",
        "value": report["gross_profit"]
    }, {
        "metric": "Total Expenses",
        "value": report["total_expenses"]
    }, {
        "metric": "Net Profit",
        "value": report["net_profit"]
    }, {
        "metric": "Margin %",
        "value": report["margin_percent"]
    }]
    
    if format == "excel":
        return create_excel_response(data, "profit_report.xlsx", ["metric", "value"])
    return create_csv_response(data, "profit_report.csv", ["metric", "value"])

# ============== SETTINGS & BACKUP ==============

@api_router.get("/settings/modules")
async def get_modules_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({"type": "modules"}, {"_id": 0})
    if not settings:
        return {
            "enable_credit_notes": True,
            "enable_debit_notes":  True,
            "enable_advanced_ims": False,
            "enable_production":   False,
        }
    # Ensure new boolean flags have defaults if missing from DB (migration safety)
    return {
        "enable_credit_notes": settings.get("enable_credit_notes", True),
        "enable_debit_notes":  settings.get("enable_debit_notes",  True),
        "enable_advanced_ims": settings.get("enable_advanced_ims", False),
        "enable_production":   settings.get("enable_production",   False),
    }

@api_router.put("/settings/modules")
async def update_modules_settings(settings: ModulesSettings, current_user: dict = Depends(get_current_user)):
    settings_doc = {
        "type": "modules",
        **settings.model_dump(),          # persist ALL fields from ModulesSettings
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.settings.update_one({"type": "modules"}, {"$set": settings_doc}, upsert=True)
    return {"message": "Module settings updated successfully"}

@api_router.get("/settings/s3")
async def get_s3_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if settings:
        # Mask the secret key
        settings["aws_secret_access_key"] = "********" if settings.get("aws_secret_access_key") else ""
    return settings or {"configured": False}

@api_router.post("/settings/s3")
async def save_s3_settings(settings: S3Settings, current_user: dict = Depends(get_current_user)):
    # Validate S3 connection
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.region
        )
        # Test connection by listing bucket
        s3_client.head_bucket(Bucket=settings.bucket_name)
    except NoCredentialsError:
        raise HTTPException(status_code=400, detail="Invalid AWS credentials")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            raise HTTPException(status_code=400, detail="Bucket not found")
        elif error_code == '403':
            raise HTTPException(status_code=400, detail="Access denied to bucket")
        raise HTTPException(status_code=400, detail=f"S3 error: {str(e)}")
    
    settings_doc = {
        "type": "s3",
        **settings.model_dump(),
        "configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.settings.update_one({"type": "s3"}, {"$set": settings_doc}, upsert=True)
    return {"message": "S3 settings saved and validated successfully"}

@api_router.post("/settings/s3/test")
async def test_s3_connection(settings: S3Settings, current_user: dict = Depends(get_current_user)):
    """Test S3 connection without saving"""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.region
        )
        s3_client.head_bucket(Bucket=settings.bucket_name)
        return {"success": True, "message": "Connection successful"}
    except NoCredentialsError:
        return {"success": False, "message": "Invalid AWS credentials"}
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return {"success": False, "message": "Bucket not found"}
        elif error_code == '403':
            return {"success": False, "message": "Access denied to bucket"}
        return {"success": False, "message": f"Error: {str(e)}"}

@api_router.get("/auth/config")
async def get_auth_config():
    """Get public authentication configuration"""
    settings = await db.settings.find_one({"type": "system"}, {"_id": 0})
    return {
        "registration_enabled": settings.get("registration_enabled", False) if settings else False
    }

@api_router.get("/settings/system")
async def get_system_settings(current_user: dict = Depends(get_current_user)):
    """Get system settings"""
    settings = await db.settings.find_one({"type": "system"}, {"_id": 0})
    if not settings:
        return {"registration_enabled": False}
    return settings

# ============== BACKUP SCHEDULE (cron) ==============

@api_router.get("/settings/backup/schedule")
async def get_backup_schedule(current_user: dict = Depends(get_current_user)):
    """Return the saved backup-schedule config (disabled if none stored)."""
    doc = await db.settings.find_one({"type": "backup_schedule"}, {"_id": 0, "type": 0, "updated_at": 0})
    if not doc:
        return BackupScheduleSettings().model_dump()
    return doc


@api_router.put("/settings/backup/schedule")
async def update_backup_schedule(
    schedule: BackupScheduleSettings,
    current_user: dict = Depends(get_current_user),
):
    """Persist a new backup-schedule and (re-)register the cron job."""
    config = schedule.model_dump()
    config_doc = {
        "type": "backup_schedule",
        **config,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.settings.update_one({"type": "backup_schedule"}, {"$set": config_doc}, upsert=True)
    # Re-register the cron job synchronously so the response reflects reality.
    apply_backup_schedule(config)
    return {"message": "Backup schedule updated", "schedule": config}

@api_router.post("/settings/system")
async def update_system_settings(settings: SystemSettings, current_user: dict = Depends(get_current_user)):
    """Update system settings"""
    settings_doc = {
        "type": "system",
        **settings.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.settings.update_one({"type": "system"}, {"$set": settings_doc}, upsert=True)
    return {"message": "System settings updated successfully"}



# Required confirmation phrase. Deliberately verbose so it can't be triggered
# by an accidental click or a single stolen token.
RESET_CONFIRMATION_PHRASE = "DELETE ALL ACCOUNTING DATA"

# In-memory rate limiter for /system/reset. Maps user_id -> last-reset epoch.
# A successful reset is permitted at most once per hour per user — enough to
# slow down an attacker that has compromised a token, while still allowing
# legitimate re-resets during testing.
_reset_cooldown_seconds = 60 * 60
_last_reset_by_user: dict = {}


@api_router.post("/system/reset")
async def reset_system(req: SystemResetRequest, current_user: dict = Depends(get_current_user)):
    """Wipe all accounting data.

    Requires three independent factors:
      1. Valid authenticated session
      2. Re-entered password
      3. Verbatim confirmation phrase
    Plus a 1-hour rate limit per user, regardless of success.
    """
    import time as _time

    user_id = current_user.get("id") or current_user.get("email")
    now = _time.time()
    last = _last_reset_by_user.get(user_id, 0)
    if now - last < _reset_cooldown_seconds:
        remaining = int(_reset_cooldown_seconds - (now - last))
        raise HTTPException(
            status_code=429,
            detail=f"Factory reset rate-limited. Try again in {remaining // 60}m {remaining % 60}s."
        )

    # Confirmation phrase check — failure also counts toward the cooldown so
    # repeated guesses can't bypass the rate limiter.
    if req.confirmation != RESET_CONFIRMATION_PHRASE:
        _last_reset_by_user[user_id] = now
        raise HTTPException(
            status_code=400,
            detail=(
                f"Confirmation phrase mismatch. To proceed, the `confirmation` "
                f"field must be exactly: '{RESET_CONFIRMATION_PHRASE}'."
            )
        )

    user = await db.users.find_one({"email": current_user.get("email")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed = user.get("password_hash") or user.get("password")
    if not hashed or not verify_password(req.password, hashed):
        _last_reset_by_user[user_id] = now
        raise HTTPException(status_code=401, detail="Incorrect password. Factory reset forbidden.")

    logger.warning(
        f"FACTORY RESET initiated by user_id={user_id} email={current_user.get('email')}"
    )
    _last_reset_by_user[user_id] = now

    cols = await db.list_collection_names()
    exempt = ["users", "settings", "backup_logs", "s3", "counters"]  # Keep logins, config, backups, and atomic counters

    deleted = {}
    for c in cols:
        if c not in exempt:
            res = await db[c].delete_many({})
            deleted[c] = res.deleted_count

    logger.warning(f"FACTORY RESET completed by user_id={user_id} deleted_counts={deleted}")
    return {"message": "Factory reset complete. All accounting data has been permanently deleted.", "details": deleted}

@api_router.post("/backup/create")
async def create_backup(current_user: dict = Depends(get_current_user)):
    """Create encrypted backup and upload to S3"""
    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")
    
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured. Please configure S3 in settings.")
    
    # Collect all data
    collections = [
        "users", "business", "customers", "products", "suppliers", "invoices", 
        "payments", "expenses", "purchases", "ledger", "stock_movements", 
        "payment_allocations", "supplier_payments",
        "credit_notes", "debit_notes", "batches", "serial_numbers",
        "bill_of_materials", "production_orders", "advance_payments", "settings"
    ]
    
    backup_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": "2.0",
        "collections": {}
    }
    
    for collection in collections:
        docs = await db[collection].find({}, {"_id": 0}).to_list(10000)
        backup_data["collections"][collection] = docs
    
    # Encrypt the backup
    json_data = json.dumps(backup_data).encode()
    encrypted_package = encrypt_data(json_data, MASTER_ENCRYPTION_KEY)
    
    # Upload to S3 — boto3 is synchronous; without to_thread it would block
    # the FastAPI event loop for the entire duration of the upload (potentially
    # many seconds for a large backup), starving every other request.
    try:
        backup_filename = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.enc"

        def _s3_upload():
            s3_client = boto3.client(
                's3',
                aws_access_key_id=s3_settings["aws_access_key_id"],
                aws_secret_access_key=s3_settings["aws_secret_access_key"],
                region_name=s3_settings.get("region", "us-east-1"),
            )
            s3_client.put_object(
                Bucket=s3_settings["bucket_name"],
                Key=f"ez-accounts-backups/{backup_filename}",
                Body=json.dumps(encrypted_package).encode(),
                ContentType="application/json",
            )

        await asyncio.to_thread(_s3_upload)
        
        # Log backup
        await db.backup_logs.insert_one({
            "id": str(uuid.uuid4()),
            "filename": backup_filename,
            "size_bytes": len(json_data),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "success"
        })
        
        return {"message": "Backup created successfully", "filename": backup_filename}
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

@api_router.get("/backup/list")
async def list_backups(current_user: dict = Depends(get_current_user)):
    """List available backups from S3"""
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        return {"backups": [], "message": "S3 not configured"}
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=s3_settings["aws_secret_access_key"],
            region_name=s3_settings.get("region", "us-east-1")
        )
        
        response = s3_client.list_objects_v2(
            Bucket=s3_settings["bucket_name"],
            Prefix="ez-accounts-backups/"
        )
        
        backups = []
        for obj in response.get("Contents", []):
            backups.append({
                "filename": obj["Key"].replace("ez-accounts-backups/", ""),
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat()
            })
        
        backups.sort(key=lambda x: x["last_modified"], reverse=True)
        return {"backups": backups}
    except Exception as e:
        return {"backups": [], "error": str(e)}

@api_router.post("/backup/restore/{filename}")
async def restore_backup(filename: str, current_user: dict = Depends(get_current_user)):
    """Restore from encrypted backup"""
    if not MASTER_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Master encryption key not configured")
    
    s3_settings = await db.settings.find_one({"type": "s3"}, {"_id": 0})
    if not s3_settings or not s3_settings.get("configured"):
        raise HTTPException(status_code=400, detail="S3 not configured")
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_settings["aws_access_key_id"],
            aws_secret_access_key=s3_settings["aws_secret_access_key"],
            region_name=s3_settings.get("region", "us-east-1")
        )
        
        response = s3_client.get_object(
            Bucket=s3_settings["bucket_name"],
            Key=f"ez-accounts-backups/{filename}"
        )
        
        encrypted_package = json.loads(response["Body"].read().decode())
        decrypted_data = decrypt_data(encrypted_package, MASTER_ENCRYPTION_KEY)
        backup_data = json.loads(decrypted_data.decode())
        
        # Restore collections.
        # 'settings' is excluded to preserve current S3/system config.
        # 'users' is excluded to prevent restoring stale passwords/accounts over live users.
        restore_exempt = {"settings", "users"}
        for collection, docs in backup_data["collections"].items():
            if collection not in restore_exempt and docs:
                await db[collection].delete_many({})
                await db[collection].insert_many(docs)
        
        return {"message": "Backup restored successfully", "restored_at": backup_data.get("created_at")}
    except Exception as e:
        logger.error(f"Restore failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

# Include the router
# ============== PHASE 3: FINANCIAL REPORTS & MAINTENANCE ==============

@api_router.post("/maintenance/fix-ledger")
async def fix_ledger_data(current_user: dict = Depends(get_current_user)):
    """One-time fix to ensure double-entry bookkeeping for historical data"""
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
        # Check cash capital
        if business.get("opening_cash", 0) > 0:
             exists = await db.ledger.find_one({"ref_type": "setup", "account": "capital", "narration": "Opening capital (cash)"})
             if not exists:
                 await create_ledger_entry("capital", 0, business["opening_cash"], "Opening capital (cash)", "setup", business["id"], business.get("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%d")))
                 fixed_counts["setup_capital"] = fixed_counts.get("setup_capital", 0) + 1
        
        # Check bank capital
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
            # Check balance type
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
        # Check Debit (Cash/Bank)
        exists_dr = await db.ledger.find_one({"ref_type": "payment", "ref_id": pay["id"], "debit": pay["amount"]})
        if not exists_dr:
             await create_ledger_entry(pay["mode"], pay["amount"], 0, f"Payment from {pay['customer_name']}", "payment", pay["id"], pay["date"])
             fixed_counts["payments"] = fixed_counts.get("payments", 0) + 1
        
        # Check Credit (Customer)
        exists_cr = await db.ledger.find_one({"ref_type": "payment", "ref_id": pay["id"], "credit": pay["amount"]})
        if not exists_cr:
             # Credit Customer
             await create_ledger_entry(f"customer:{pay['customer_id']}", 0, pay["amount"], "Payment received", "payment", pay["id"], pay["date"])
             fixed_counts["payments"] = fixed_counts.get("payments", 0) + 1

    return {"message": "Ledger fixed successfully", "counts": fixed_counts}

@api_router.get("/reports/trial-balance")
async def get_trial_balance(current_user: dict = Depends(get_current_user)):
    """Get Trial Balance (Sum of distinct accounts)"""
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

@api_router.get("/reports/balance-sheet")
async def get_balance_sheet(current_user: dict = Depends(get_current_user)):
    """Get Balance Sheet (Assets, Liabilities, Equity)"""
    
    # 1. Calculate Ledger Balances
    pipeline = [
        {"$group": {
            "_id": "$account",
            "balance": {"$sum": {"$subtract": ["$debit", "$credit"]}}
        }}
    ]
    balances = {doc["_id"]: doc["balance"] for doc in await db.ledger.aggregate(pipeline).to_list(None)}
    
    # helper
    def get_bal(key): return balances.get(key, 0)
    def get_prefix_sum(prefix): return sum(v for k, v in balances.items() if k.startswith(prefix))

    # 2. Assets
    # Cash & Bank
    cash = get_bal("cash")
    bank = get_bal("bank")
    
    # Accounts Receivable (Sum of all customer:* accounts)
    accounts_receivable = get_prefix_sum("customer:")
    
    # Inventory Value (Calculated from Products, not Ledger, for accuracy in this simplified system)
    # Note: In a pure double-entry, we would track this in ledger, but here we use Periodic Inventory for P&L
    # and "Stock on Hand" for Balance Sheet. 
    # To balance the equation, "Closing Stock" affects Equity (Retained Earnings).
    products = await db.products.find({}, {"cost_price": 1, "stock": 1}).to_list(None)
    inventory_value = sum((p.get("cost_price", 0) or 0) * (p.get("stock", 0) or 0) for p in products)

    total_assets = cash + bank + accounts_receivable + inventory_value
    
    # 3. Liabilities
    # Accounts Payable (Sum of all supplier:* accounts)
    # Note: Supplier accounts are usually Credit balance (negative in our logic? No, Ledger logic: Debit - Credit)
    # If using Debit - Credit:
    # Asset (Debit nature): Positive
    # Liability (Credit nature): Negative
    # Income (Credit nature): Negative
    # Expense (Debit nature): Positive
    
    # So AP will be negative. We want to show it as positive Liability.
    accounts_payable_raw = get_prefix_sum("supplier:")
    accounts_payable = -accounts_payable_raw # Flip sign to show as positive liability amount
    
    # Customer Credits (Liability)
    customer_credits_raw = get_prefix_sum("customer_credit:")
    customer_credits = -customer_credits_raw
    
    total_liabilities = accounts_payable + customer_credits
    
    # 4. Equity
    # Net Profit = Income - Expenses
    # Income (Credit nature, so negative)
    sales = -get_bal("sales")
    
    # Expenses (Debit nature, so positive)
    purchases = get_bal("purchases")
    expenses_total = get_prefix_sum("expense:")
    
    # COGS for P&L = Opening Stock + Purchases - Closing Stock
    # For Balance Sheet Equity, we typically add Net Profit.
    # Net Profit = Sales - (Purchases - Change in Inventory) - Expenses
    # Change in Inventory = Closing Stock - Opening Stock
    # Simplified: Net Profit = Sales - Purchases - Expenses + (Closing Stock - Opening Stock)
    # We assume Opening Stock was 0 or handled in Capital. simpler:
    # Equity = Capital + Retained Earnings
    # Retained Earnings = Net Profit
    
    # Let's calculate Net Profit correctly
    # Opening Stock? We don't verify date range here, it's "As of Today".
    # So Opening Stock is effectively 0 (start of time).
    opening_stock = 0 
    closing_stock = inventory_value
    
    cost_of_goods_sold = opening_stock + purchases - closing_stock
    gross_profit = sales - cost_of_goods_sold
    net_profit = gross_profit - expenses_total
    
    # Capital (if we had it). For now, Equity matches Assets - Liabilities
    # Equity = Total Assets - Total Liabilities
    # Check: Does Net Profit match this?
    # Assets = Liab + Equity
    # Equity = Assets - Liab
    # Equity = (Cash + Bank + AR + STOCK) - (AP + Credits)
    # Net Profit = Sales - (Purchases - STOCK) - Expenses
    #            = Sales - Purchases + STOCK - Expenses
    # Ledger Equation:
    # 0 = Cash + Bank + AR + Exp + Pur + AP_raw + Sales_raw + Capital_raw
    # 0 = (Cash+Bank+AR) + (Exp+Pur) + (-AP) + (-Sales)
    # => Cash+Bank+AR = AP + Sales - Exp - Pur
    # Add Stock to both sides?
    # Assets = (Cash+Bank+AR) + Stock
    #        = AP + Sales - Exp - Pur + Stock
    #        = AP + (Sales - Exp - Pur + Stock)
    #        = Liab + Net Profit
    # Yes! It balances!
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    opening_stock = 0 
    closing_stock = inventory_value
    
    cost_of_goods_sold = opening_stock + purchases - closing_stock
    gross_profit = sales - cost_of_goods_sold
    net_profit = gross_profit - expenses_total
    
    # Capital
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

# ============== AI FEATURES ==============

@api_router.post("/ai/parse-invoice")
async def parse_invoice_endpoint(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    try:
        content_type = file.content_type
        
        # Check if it's an image or PDF
        if content_type not in ["image/jpeg", "image/png", "application/pdf"]:
            # For now, simplistic check. gpt-4o handles images best. PDF needs conversion or preview.
            # If PDF, we might need to convert to image first or extract text. 
            # For this MVP, let's assume Images. If PDF, we might return error or try.
            pass

        data = await parse_invoice_image(file)
        return data

    except HTTPException:
        raise
    except Exception as e:
        # Don't leak internal exception details to the client.
        logger.exception(f"AI Parse Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to parse invoice. Please try again.")


# ============== VOICE ASSISTANT WEBSOCKET ENDPOINT ==============

@app.websocket("/ws/voice")
async def voice_assistant_websocket(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket endpoint for voice assistant.

    Authentication: the client opens the socket, then sends an auth message
    as its FIRST frame: {"type": "auth", "token": "<jwt>"}.

    Passing the token via a URL query parameter (?token=...) is also accepted
    for backwards compatibility, but is deprecated — query strings get logged
    by reverse proxies and stored in browser history, so the JWT leaks.
    """
    await websocket.accept()
    user_id: Optional[str] = None

    # ---- Path A: legacy ?token= query param ----
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
        if not user_id:
            await websocket.send_json({"type": "auth_failed", "message": "Invalid token"})
            await websocket.close(code=1008, reason="Invalid token")
            return
        logger.warning(
            "Voice WS: deprecated query-string token used. "
            "Client should send {type:'auth', token:...} as first message instead."
        )
    else:
        # ---- Path B: token in first-message handshake (preferred) ----
        await websocket.send_json({"type": "auth_required"})
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Auth timeout")
            return
        except WebSocketDisconnect:
            return
        if not isinstance(first, dict) or first.get("type") != "auth" or not first.get("token"):
            await websocket.send_json({"type": "auth_failed", "message": "Expected {type:'auth', token:...} as first message"})
            await websocket.close(code=1008, reason="Auth required")
            return
        try:
            payload = jwt.decode(first["token"], SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
        if not user_id:
            await websocket.send_json({"type": "auth_failed", "message": "Invalid token"})
            await websocket.close(code=1008, reason="Invalid token")
            return

    # ---- Authenticated — start session ----
    # NB: `ws_session_manager.connect()` will call `websocket.accept()` again
    # internally — that is a no-op on an already-accepted socket. To avoid the
    # double-accept we resume/create the session manually using the manager's
    # primitives below.
    try:
        # The manager's connect() also accepts the socket; we already accepted
        # it above (so we could send/receive the auth handshake). Call connect
        # which is idempotent on accept and registers the session.
        session = await ws_session_manager.connect(user_id, websocket)
        logger.info(f"Voice assistant connected: user={user_id}, session={session.session_id}")

        # Main message loop
        while True:
            data = await websocket.receive_json()
            response = await ws_session_manager.process_message(user_id, data)
            await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info(f"Voice assistant disconnected: user={user_id}")
        await ws_session_manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Voice assistant error: user={user_id}, error={str(e)}")
        await ws_session_manager.disconnect(user_id)
        await websocket.close(code=1011, reason="Internal error")


@api_router.get("/voice/stats")
async def get_voice_stats(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get voice assistant statistics.
    
    Returns:
        Active sessions, states, etc.
    """
    # Verify token
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    stats = ws_session_manager.get_session_stats()
    return stats


# Health moved to app/routers/health.py (Phase 2).

app.include_router(api_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(business_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(suppliers_router)
app.include_router(bom_router)
app.include_router(production_router)
app.include_router(purchases_router)
app.include_router(invoices_router)
app.include_router(payments_router)
app.include_router(credit_notes_router)
app.include_router(debit_notes_router)

# CORS — explicit origin list required when credentials are enabled.
# Browsers reject `*` + credentials per the CORS spec, so we never allow that combo.
_cors_origins_raw = os.environ.get('CORS_ORIGINS', '').strip()
if _cors_origins_raw and _cors_origins_raw != '*':
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(',') if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # No explicit origins configured — fall back to wildcard WITHOUT credentials.
    # This still lets public endpoints work in dev but disables credentialed
    # cross-origin requests until CORS_ORIGINS is set explicitly.
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=False,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Note: client.close() is handled by the lifespan context manager above;
# the old @app.on_event("shutdown") handler caused a double close.

