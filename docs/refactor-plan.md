# Backend refactor plan — break up the monolithic `server.py`

## Why

`backend/server.py` is currently **5,639 lines** with **112 REST endpoints**, **133 helper functions**, and **41 Pydantic models** in a single file. Git blame is meaningless, parallel PRs conflict on every change, and onboarding takes hours just to find what you're looking for.

## Target structure

```
backend/
  server.py                    # ~150 lines: app factory, lifespan, include_routers
  app/
    config.py                  # env validation, secrets, FIDO RP config
    database.py                # Motor client + `db` handle
    deps.py                    # FastAPI deps: get_current_user, security
    lifespan.py                # startup: indexes, counter seeding, scheduler boot
    schemas/                   # 41 Pydantic models, split by domain
      common.py · product.py · customer.py · supplier.py
      invoice.py · purchase.py · payment.py
      credit_note.py · debit_note.py · expense.py
      bom.py · production.py · webauthn.py · settings.py · business.py
    services/                  # business-logic helpers (not routes)
      auth.py                  # password/JWT helpers
      crypto.py                # encrypt_data / decrypt_data
      money.py                 # _money rounding helper
      ledger.py                # create_ledger_entry, get_account_balance
      stock.py                 # create_stock_movement, get_product_stock
      counters.py              # _next_seq + ref-number generators
      payments_apply.py        # apply_payment_fifo, apply_credit_note_to_invoice
      passkey.py               # fido_server, _b64url_to_bytes, etc.
      backup.py                # scheduled_backup_job, apply_backup_schedule
      ai_service.py            # (existing — keep)
      function_executor.py     # (existing — keep)
      voice_*.py               # (existing — keep)
    routers/                   # one FastAPI APIRouter per domain
      health.py · auth.py · business.py
      products.py · customers.py · suppliers.py
      bom.py · production.py
      purchases.py · invoices.py · payments.py
      credit_notes.py · debit_notes.py · expenses.py
      dashboard.py · reports.py · exports.py
      settings.py · backup_schedule.py
      ai.py · voice_ws.py
```

## Dependency rules (enforce strictly)

```
routers/  →  services/  →  schemas/  →  database/config
```

- Routers may import services.
- Services may import schemas, database, config — never routers.
- Schemas import nothing from the app (pure Pydantic).
- No circular imports. If you find one, the helper belongs in a shared module higher up.

## Migration phases (each independently shippable)

### Phase 0 — Scaffolding (this PR)
Pure file moves, zero behaviour change.
- Create `app/` directory tree.
- Move config, db client, `get_current_user` to `app/config.py`, `app/database.py`, `app/deps.py`.
- Move all 41 Pydantic models to `app/schemas/*.py`.
- `server.py` imports them; everything still works.
- Verify: server boots, `/api/auth/config` returns 200, login still works.

### Phase 1 — Extract services (this PR)
Helpers move out of `server.py` into `app/services/*.py`. Route handlers stay in `server.py` and import what they need from services.
- All cross-cutting helpers (auth, crypto, ledger, stock, money, counters, payments-apply, passkey, scheduler) move.
- `server.py` shrinks dramatically; route handlers reference `from app.services.X import Y`.
- Verify: live smoke test of every fix already documented in FIXES.md still passes.

### Phase 2 — Routers (one domain per PR, future work)
- Cut each domain's endpoints out of `server.py` into `app/routers/<domain>.py` with its own `APIRouter`.
- Register in `server.py` via `app.include_router(routers.invoices.router)`.
- Order (lowest coupling → highest):
  1. health, auth, business
  2. products, customers, suppliers
  3. bom, production
  4. purchases, invoices
  5. payments, credit_notes, debit_notes
  6. expenses, dashboard, reports, exports
  7. settings, backup_schedule, ai, voice_ws

### Phase 3 — Final shape
`server.py` becomes: config load → app create → lifespan → CORS → ~20 `include_router` calls. Around 150 lines.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Circular imports | Strict rule: routers → services → schemas. Enforce in code review. |
| Helpers used across many domains | Live in `services/`, never in any router. Single source of truth. |
| Existing scripts (`fix_password.py`, `verify_*.py`, `test_fido.py`) reference `server.SYMBOL` | `server.py` keeps re-exports during Phases 0/1 so external scripts don't break. |
| Lifespan ordering (indexes → counter seed → scheduler → BOM backfill) | Encapsulate in `app/lifespan.py` as ordered functions; trivial to read. |
| Git diff noise (looks like delete+add) | Use `git log --follow` and `git diff -M` flags. PR descriptions explicitly state "Phase N — file moves only." |

## What this is NOT

- Not a rewrite. All logic preserved verbatim.
- Not a class-based-views migration. FastAPI works great with functions.
- Not a chance to add features. Refactor and ship; features come later.
- Not big-bang. Each phase is independently revertable.
