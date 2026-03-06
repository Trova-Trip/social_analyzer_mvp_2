# Social Analyzer MVP 2

## Local Development

- `make dev` — start local environment (Redis + Flask + RQ worker, mock adapters, seeds test data)
- `make dev-stop` — shut everything down
- `make dev-reset` — wipe DB + Redis and restart fresh
- `make test` — run pytest
- All commands use `.venv/bin/` — never rely on global python/pip/flask/rq
- Port 5001 (macOS AirPlay occupies 5000)
- No Docker required. SQLite by default, `MOCK_PIPELINE=1` for all adapters

## Architecture

6-stage pipeline: discovery → prescreen → enrichment → analysis → scoring → crm_sync

Key files:
- `app/pipeline/mock_adapters.py` — mock adapters, MUST match `_standardize_results()` field names
- `app/services/insightiq.py:404-438` — `_standardize_results()` is the canonical field contract
- `app/services/db.py:92-106` — fallback chains for field resolution (handles both formats but mocks should not rely on this)
- `app/pipeline/crm.py` — CRM sync, guards on `HUBSPOT_WEBHOOK_URL` / `HUBSPOT_API_KEY` (skips gracefully when unset)
- `app/config.py` — all env vars centralized here

## Important Patterns

- **Mock-to-production parity**: mock adapters must output the exact same field names as real APIs. Run `pytest tests/app/pipeline/test_mock_parity.py` to verify. Do not add fields to mocks that don't exist in real responses.
- **External service guards**: when an API key is unset, the stage should skip gracefully (log warning, return profiles unchanged). Never let a None URL reach `requests.post()`.
- **Discovery cap**: `STAGING_DISCOVERY_CAP` env var limits max_results across all discovery adapters. Not set in production.

## Testing

- Run full suite: `make test` or `.venv/bin/python -m pytest`
- Tests use in-memory SQLite via conftest.py fixtures
- `sample_profiles` fixture uses InsightIQ format — keep it in sync with `_standardize_results()`

## Railway Deployment

- **Project**: `selfless-freedom` — two environments: `production`, `staging`
- Each environment has its own services (`web`, `worker`) and databases (Postgres, Redis)
- `staging` branch deploys to staging, `main` deploys to production
- Start commands are set in Railway dashboard (not in code — `railway.toml` doesn't support per-service config)
  - web: `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 2 --worker-class gthread`
  - worker: `rq worker-pool --url $REDIS_URL --num-workers 4`
- Pre-deploy runs `alembic upgrade head` automatically
- Staging has no HubSpot keys (CRM sync skips) and discovery capped at 25
