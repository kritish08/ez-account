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
from app.routers.expenses import router as expenses_router
from app.routers.dashboard import router as dashboard_router
from app.routers.reports import router as reports_router
from app.routers.exports import router as exports_router
from app.routers.settings import router as settings_router
from app.routers.backup import router as backup_router
from app.routers.financial import router as financial_router
from app.routers.ai import router as ai_router
from app.routers.voice import router as voice_router

from app import voice_state

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WebSocketSessionManager is instantiated inside lifespan because its
# __init__ schedules a background task and needs a running event loop.
# The instance is published via app.voice_state for the voice router.
from services.websocket_session_manager import WebSocketSessionManager

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
    voice_state.set_manager(WebSocketSessionManager(db))

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

# ============== EXPENSES + DASHBOARD + REPORTS + EXPORTS ROUTES ==============
# Moved to app/routers/{expenses,dashboard,reports,exports}.py — see Phase 2 imports.

# ============== SETTINGS + BACKUP + FINANCIAL + AI + VOICE ROUTES ==============
# Moved to app/routers/{settings,backup,financial,ai,voice}.py — see Phase 2 imports.

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
app.include_router(expenses_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(exports_router)
app.include_router(settings_router)
app.include_router(backup_router)
app.include_router(financial_router)
app.include_router(ai_router)
app.include_router(voice_router)

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

