# OARS Student Solutions

Mobile-first PWA for Ugandan university students: academic resources, printing, and campus services.
By OARS Technologies.

**Status: Phases 1-9 written (foundation, database, auth/RBAC, academic structure, resources, premium access, search, printing, payments), mostly not yet verified by execution.**
Run `scripts/verify-phase1.sh` (it covers the whole repo). See `docs/identity.md` (auth, RBAC) and `docs/resources.md`
(academic structure, resources, downloads, search) and `docs/printing-payments.md` (printing, payments) for design, endpoints and known limitations.

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query, Zod, Workbox (via vite-plugin-pwa) |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Alembic |
| Database | PostgreSQL 16 |
| Local services | Docker Compose (Postgres, MinIO) |

Architecture: modular monolith.

## Prerequisites

Python 3.12+, Node.js 20.19+ (22 recommended), Docker with Compose.

## Quick start

```bash
# 1. Environment
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET_KEY in .env

# 2. Postgres + MinIO
docker compose up -d

# 3. Backend (terminal 1)
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ruff format .                        # one-time: normalise formatting before first commit
alembic upgrade head
python -m app.cli create-platform-admin --email you@example.com --name "Your Name"   # first admin
python -m app.cli seed-demo        # optional: demo users, resources and a print shop (development only)
uvicorn app.main:create_app --factory --reload --no-access-log

# 4. Frontend (terminal 2)
cd frontend
npm install                          # creates package-lock.json: commit it (CI uses `npm ci`)
cd
```

- API docs (development only): http://localhost:8000/docs
- Web app: http://localhost:5173 (status page at `/status` calls the real `/api/v1/ready`)

If the Postgres volume existed before the test-DB init script was added, create the test DB once:

```bash
docker compose exec postgres psql -U oars -d oars -c "CREATE DATABASE oars_test;"
```

## Commands

Backend (from `backend/`, venv active):

```bash
ruff check . && ruff format --check .
mypy app
pytest                          # all tests (needs Postgres; DB tests are marked `integration`)
pytest -m "not integration"     # without a database
alembic upgrade head && alembic check
```

Frontend (from `frontend/`):

```bash
npm run typecheck && npm run lint && npm test && npm run build
```

Everything at once (from repo root): `scripts/verify-phase1.sh`

End-to-end (optional, from `frontend/`): `npx playwright install chromium && npm run e2e` (see `docs/resources.md`).

## API conventions

- Base path `/api/v1`. Probes `/health` and `/ready` also exist unversioned.
- Success: `{ "data": ..., "meta": {} }`
- Error: `{ "error": { "code": "...", "message": "...", "details": [{"field","message"}] | null, "request_id": "..." } }`
- Every response carries `X-Request-ID`. Unhandled errors never expose internals.
- Authorization (Phase 4+) is permission-based; handlers never branch on role names.

## Database conventions

UUID primary keys (`UUIDPrimaryKeyMixin`), timezone-aware `created_at`/`updated_at` (`TimestampMixin`),
deterministic constraint names (see `app/db/base.py`), money as integer UGX. Models must be imported in
`app/db/registry.py` so Alembic autogenerate sees them. CI runs `alembic check`, so model changes
without a migration fail the build.

## Security notes (foundation)

Secrets come only from environment variables; the frontend contains none (only `VITE_`-prefixed,
non-secret values are exposed to the browser). Settings validation refuses weak secrets, wildcard CORS,
and non-HTTPS origins in production. Logs redact sensitive keys. Security headers are set on every response.

## Roadmap

Done (Phases 1-9): foundation/auth, academic structure/resources/search, printing and payments (FakeProvider only).  
Done (Phases 10-13): student dashboard, notifications, admin panel, advertising, analytics, PWA with service worker.  
Next: 14+ MVP verification, real payment provider integration, production hardening.
