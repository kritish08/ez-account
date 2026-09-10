# EZ Account

A production-focused **full-stack accounting and inventory platform** for small and growing businesses, with clean UX, secure backend design, and practical automation for day-to-day operations.

Built for real usage patterns: invoices, purchases, ledgers, stock movement, production orders, GST-ready flows, passkey authentication, AI-assisted invoice parsing, and encrypted cloud backup/restore.

---

## Why this project stands out

- **Domain-complete scope**: accounting + inventory + production in one system
- **Security-first implementation**: passkeys, token revocation, encryption-at-rest, destructive-action safeguards
- **Operational maturity**: CI pipeline, health checks, route splitting, Dockerized deployment, backup scheduling
- **Performance-aware backend**: aggregation-first reporting, reduced N+1 queries, indexed collections, atomic transitions

---

## Core capabilities

### Finance & accounting
- Business setup and configurable system settings
- Customer and supplier lifecycle management with ledgers
- Sales invoices with draft/publish flow, PDF generation, and auto numbering
- Payments with allocation workflows
- Credit notes and debit notes
- Expense tracking with category breakdowns
- Financial reports (outstanding, credit, profit, P&L, trial balance, balance sheet)

### Inventory & production
- Raw materials and finished goods management
- Stock movement tracking and low-stock reporting
- Batch and serial support
- Bill of Materials (BOM) mapping
- Production order lifecycle: `PLANNED → IN_PROGRESS → QC → COMPLETED/CANCELLED`

### AI & automation
- AI invoice parsing endpoint for image/PDF-based extraction
- Voice assistant over WebSocket with authenticated session flow
- Automated encrypted S3 backups with scheduler + secure restore controls

### Security & access
- JWT auth with token versioning and per-token denylist revocation
- Passkey/WebAuthn registration and authentication flows
- Login throttling and AI quota/rate limiting
- Factory reset and backup restore gated by admin check + password + confirmation phrase + cooldown

---

## Tech stack

- **Frontend**: React 19, React Router, Tailwind CSS, Radix UI, CRACO
- **Backend**: FastAPI, Motor (MongoDB), Pydantic, APScheduler
- **Database**: MongoDB
- **Infra**: Docker, Docker Compose, Nginx, Traefik-ready labels
- **Testing/CI**: Pytest + GitHub Actions

---

## Repository structure

```text
ez-account/
├── backend/        # FastAPI app, routers/services/schemas, tests
├── frontend/       # React app (route-split pages + UI components)
├── backup/         # Scheduled encrypted backup container
├── compose.yaml    # Production-style multi-service orchestration
└── .github/workflows/test.yml
```

---

## Getting started

### 1) Prerequisites

- Python 3.11+
- Node.js 20+
- MongoDB (or MongoDB Atlas URI)
- Docker + Docker Compose (recommended for full stack)

### 2) Backend setup (local)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.production.example .env
```

Update `.env` with valid values (especially `MONGO_URL`, `JWT_SECRET`, `CORS_ORIGINS`), then run:

```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 3) Frontend setup (local)

```bash
cd frontend
npm ci --legacy-peer-deps
```

Create `.env` in `frontend/`:

```bash
REACT_APP_BACKEND_URL=http://localhost:8001
```

Run:

```bash
npm start
```

---

## Run with Docker Compose

From repository root:

```bash
cp .env.production.template backend/.env
docker compose up -d --build
```

Services:
- Frontend: `http://localhost` (or your mapped host)
- Backend API: `http://localhost:8001`
- Health: `/health` and `/api/health`

---

## Testing and quality checks

### Backend tests

```bash
cd backend
pytest -v
```

The backend contains an extensive `tests/` suite covering auth, invoices, products, notes, backups, rate limits, health checks, and security behavior.

### Frontend build validation

```bash
cd frontend
npm run build
```

CI pipeline (`.github/workflows/test.yml`) validates:
- Backend test suite
- Frontend production build
- Build hygiene/security checks (tracked `.env` and credential-bearing file guards)

---

## API surface (high level)

Core router groups include:
- `auth`, `business`, `customers`, `suppliers`
- `products`, `bom`, `production`, `purchases`
- `invoices`, `payments`, `credit-notes`, `debit-notes`, `expenses`
- `dashboard`, `reports`, `financial`, `exports`
- `settings`, `backup`, `ai`, `voice`, `health`

Interactive API docs are available at `/docs` when the backend is running.

---

## Production and security notes

- `CORS_ORIGINS` is required and wildcard is explicitly rejected
- Secrets for OpenAI and S3 are encrypted before storage
- Backup archives are encrypted and uploaded to S3
- Token revocation supports both single-session and global logout
- Passkey support is first-class for modern phishing-resistant login

---

## Project status

Actively evolving toward a robust SMB accounting platform with strong backend rigor and practical AI integrations.

If you’re reviewing this project as a recruiter or hiring manager: this codebase demonstrates full-stack delivery, security awareness, performance-minded backend work, and production-readiness decisions beyond CRUD basics.
