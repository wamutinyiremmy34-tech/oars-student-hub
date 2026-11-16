#!/usr/bin/env bash
# Phase 1 verification. Run from repo root, backend venv active, `docker compose up -d` already done.
set -u
fail=0
run() { local name="$1"; shift; echo; echo "=== $name"; echo "\$ $*"
  if "$@"; then echo "--> PASS: $name"; else echo "--> FAIL: $name"; fail=1; fi; }

live_api() {
  (cd backend && uvicorn app.main:create_app --factory --port 8000 --no-access-log \
     >/tmp/oars-uvicorn.log 2>&1 & echo $! >/tmp/oars-uvicorn.pid)
  sleep 4
  curl -fsS localhost:8000/health && echo && curl -fsS localhost:8000/api/v1/ready && echo
  local rc=$?
  kill "$(cat /tmp/oars-uvicorn.pid)" 2>/dev/null
  return $rc
}

run "compose config valid"       docker compose config -q
run "compose services healthy"   bash -c 'docker compose ps --format "{{.Name}} {{.Health}}"'
run "backend: app imports/init"  bash -c 'cd backend && python -c "from app.main import create_app; create_app(); print(\"app created\")"'
run "backend: ruff lint"         bash -c 'cd backend && ruff check .'
run "backend: ruff format"       bash -c 'cd backend && ruff format --check .'
run "backend: mypy"              bash -c 'cd backend && mypy app'
run "backend: alembic upgrade"   bash -c 'cd backend && alembic upgrade head'
run "backend: alembic check"     bash -c 'cd backend && alembic check'
run "backend: migration down/up" bash -c 'cd backend && alembic downgrade base && alembic upgrade head && alembic check'
run "backend: pytest (all)"      bash -c 'cd backend && pytest -v'
run "backend: pytest (no DB)"    bash -c 'cd backend && pytest -m "not integration" -q'
run "backend: live /health+/ready" live_api
if [ -f frontend/package-lock.json ]; then FE_INSTALL="npm ci"; else FE_INSTALL="npm install"; fi
run "frontend: install"          bash -c "cd frontend && $FE_INSTALL"
run "frontend: typecheck"        bash -c 'cd frontend && npm run typecheck'
run "frontend: eslint"           bash -c 'cd frontend && npm run lint'
run "frontend: vitest"           bash -c 'cd frontend && npm test'
run "frontend: build"            bash -c 'cd frontend && npm run build'
run "frontend: PWA artifacts"    bash -c 'test -f frontend/dist/manifest.webmanifest && test -f frontend/dist/sw.js && echo "manifest + sw.js present"'
run "frontend: Tailwind output"  bash -c 'grep -l "rounded-control\|--color-primary" frontend/dist/assets/*.css'

echo; [ $fail -eq 0 ] && echo "ALL PHASE 1 CHECKS PASSED" || echo "SOME CHECKS FAILED (see above)"
exit $fail
