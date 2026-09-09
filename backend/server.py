"""EZ Accounts by Kyrex — FastAPI app factory + lifespan.

After the Phase 0–2 refactor this file is a thin shell:
- Lifespan handler: create indexes, seed atomic counters, run one-time
  migrations, start the APScheduler cron, publish the WebSocket session
  manager into app.voice_state.
- App construction: static `/api/uploads`, CORS, and `include_router`
  for the 19 domain routers under `app/routers/`.

All business logic and route handlers live under the `app/` package
(routers → services → schemas → database/config). This module imports
nothing it doesn't actually use — every helper it needs lives in
`app.services.*` or in `app/`.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pymongo import ASCENDING, DESCENDING

from app import voice_state
from app.config import CORS_ORIGINS
from app.database import client, db
from app.services.backup import apply_backup_schedule, scheduler

# Domain routers — wired in via app.include_router below.
from app.routers.ai import router as ai_router
from app.routers.auth import router as auth_router
from app.routers.backup import router as backup_router
from app.routers.bom import router as bom_router
from app.routers.business import router as business_router
from app.routers.credit_notes import router as credit_notes_router
from app.routers.customers import router as customers_router
from app.routers.dashboard import router as dashboard_router
from app.routers.debit_notes import router as debit_notes_router
from app.routers.expenses import router as expenses_router
from app.routers.exports import router as exports_router
from app.routers.financial import router as financial_router
from app.routers.health import router as health_router
from app.routers.invoices import router as invoices_router
from app.routers.payments import router as payments_router
from app.routers.production import router as production_router
from app.routers.products import router as products_router
from app.routers.purchases import router as purchases_router
from app.routers.reports import router as reports_router
from app.routers.settings import router as settings_router
from app.routers.suppliers import router as suppliers_router
from app.routers.voice import router as voice_router

# WebSocketSessionManager is instantiated inside lifespan because its __init__
# schedules a background task and needs a running event loop. The instance is
# published via app.voice_state for the voice router to consume.
from services.websocket_session_manager import WebSocketSessionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _safe_create_index(coll_name: str, keys, **kwargs):
    """Create a Mongo index, logging (not raising) on failure so one bad index
    doesn't prevent the rest from being created."""
    try:
        await db[coll_name].create_index(keys, **kwargs)
    except Exception as e:
        logger.warning(f"Index create failed on {coll_name} {keys}: {e}")


async def _seed_counter_from_max(counter_name: str, coll_name: str, field: str, prefix: str):
    """One-time seed of the atomic counter from the existing max value in the
    collection. Uses $max so it's idempotent and safe to call on every boot."""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting up...")

    # The voice assistant is an optional add-on; the accounting app must boot
    # without it. Constructing the manager builds an AI client that raises if
    # its credentials are missing or malformed, and an unguarded call here
    # killed the whole API at startup over a voice-only config problem. The
    # voice routes already handle a None manager by returning 503 — that path
    # was simply unreachable because the process died first.
    try:
        voice_state.set_manager(WebSocketSessionManager(db))
    except Exception as e:
        logger.warning(
            "Voice assistant unavailable — continuing without it. "
            "Voice endpoints will return 503. Cause: %s: %s",
            type(e).__name__, e,
        )

    # ---- Indexes ----
    # Hot-path lookups by id and email. Without these every authenticated
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

    await _safe_create_index("ledger", [("account", ASCENDING), ("date", DESCENDING)])
    await _safe_create_index("ledger", [("ref_type", ASCENDING), ("ref_id", ASCENDING)])
    await _safe_create_index("stock_movements", [("product_id", ASCENDING), ("date", DESCENDING)])
    await _safe_create_index("stock_movements", [("ref_type", ASCENDING), ("ref_id", ASCENDING)])
    await _safe_create_index("invoices", [("customer_id", ASCENDING), ("status", ASCENDING), ("date", DESCENDING)])
    await _safe_create_index("production_orders", [("status", ASCENDING), ("product_id", ASCENDING)])

    # Unique reference-number indexes — partial filter so legacy docs missing
    # the field don't break index creation.
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

    # Serial / batch uniqueness per product.
    await _safe_create_index("serial_numbers",
                             [("product_id", ASCENDING), ("serial_number", ASCENDING)],
                             unique=True,
                             partialFilterExpression={"serial_number": {"$exists": True}})
    await _safe_create_index("batches",
                             [("product_id", ASCENDING), ("batch_number", ASCENDING)],
                             unique=True,
                             partialFilterExpression={"batch_number": {"$exists": True}})

    # Counter doc primary key. Mongo gives _id a unique index automatically;
    # this just makes the intent explicit and creates the collection eagerly.
    await _safe_create_index("counters", "_id")

    # WebAuthn challenge state — TTL index on expires_at cleans up stale
    # registration/auth handshakes (5-min window) so abandoned flows don't
    # accumulate. Also index the lookup keys.
    await _safe_create_index("webauthn_states", "expires_at", expireAfterSeconds=0)

    # Revoked-token denylist, consulted on every authenticated request, so the
    # jti lookup must be indexed. The TTL sweep drops each row once the token
    # it denies has expired on its own — the denylist never grows unbounded
    # and never needs to outlive its tokens.
    await _safe_create_index("revoked_tokens", "jti", unique=True)
    await _safe_create_index("revoked_tokens", "expires_at", expireAfterSeconds=0)
    await _safe_create_index("webauthn_states", [("user_id", ASCENDING), ("type", ASCENDING)])
    await _safe_create_index("webauthn_states", [("email", ASCENDING), ("type", ASCENDING)])
    # Credential ids are globally unique per the WebAuthn spec, so a plain
    # unique index is fine.
    await _safe_create_index("users", "passkeys.id",
                             partialFilterExpression={"passkeys.id": {"$exists": True}})

    # Seed atomic counters from the existing highest reference numbers so the
    # new generator picks up where the old (racey) generator left off.
    await _seed_counter_from_max("invoice", "invoices", "invoice_number", "INV-")
    await _seed_counter_from_max("purchase", "purchases", "purchase_number", "PUR-")
    await _seed_counter_from_max("credit_note", "credit_notes", "credit_note_number", "CN-")
    await _seed_counter_from_max("debit_note", "debit_notes", "debit_note_number", "DN-")
    await _seed_counter_from_max("production_order", "production_orders", "order_number", "WO-")

    # One-time migration: backfill `id` on BOMs created before the stable-id
    # fix. Without an id, production_orders.bom_id is always null because the
    # order copies it via `bom["id"] if bom and "id" in bom else None`.
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

# Static files for user uploads (invoice attachments, etc.).
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Domain routers.
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

# CORS — always an explicit origin list. config.parse_cors_origins refuses
# to start on a missing value or a wildcard, so there is no permissive
# fallback to drift into.
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
