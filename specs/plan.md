# Implementation Plan

Mark tasks with `[x]` as you complete them. Work phases top-to-bottom; each phase's output is a dependency for the next.

---

## Phase 0: Project Setup

- [x] Add all runtime and dev dependencies to `pyproject.toml`
- [x] Create `.env.example` with all configuration variables
- [x] Create `docker-compose.yml` with the `postgres` service
- [x] Run `alembic init alembic` to scaffold `alembic.ini` and `alembic/`
- [x] Scaffold all package directories with `__init__.py` files (`core/`, `django_api/`, `django_api/config/`, `django_api/satellites/`, `litestar_api/`, `litestar_api/satellites/`, `tests/`)

---

## Phase 1: Core Data Layer

- [x] `core/logging_config.py` — `setup_logging()` using `python-json-logger`
- [x] `core/models.py` — `Satellite`, `TleRecord`, `ProcessedTle` SQLAlchemy models with all constraints and relationships
- [x] `core/database.py` — `engine`, `SessionLocal`, and `get_session()` context manager
- [x] `alembic/env.py` — configure to import `core.models.Base.metadata` for autogenerate
- [x] Generate initial Alembic migration: `alembic revision --autogenerate -m "initial schema"`
- [x] Verify migration applies cleanly against running Postgres: `alembic upgrade head`

---

## Phase 2: Data Ingestion

- [x] `core/ingestion.py` — `SATELLITE_TARGETS` constant (ISS NORAD 25544, NOAA 19 NORAD 33591)
- [x] `core/ingestion.py` — `fetch_tle(norad_id, client)` with 3x retry and exponential backoff
- [x] `core/ingestion.py` — `ingest_satellites(session, fetched_at=None)` with upsert and dedup logic
- [x] Smoke test: call `ingest_satellites` against live API; verify `satellites` and `tle_records` rows in DB

---

## Phase 3: Data Processing

- [ ] `core/processing.py` — `compute_orbital_params(tle_line1, tle_line2)` using `sgp4`
- [ ] `core/processing.py` — `classify_orbit(apogee_km, perigee_km, eccentricity)` classification logic
- [ ] `core/processing.py` — `process_unprocessed(session)` batch processor
- [ ] Smoke test: call `process_unprocessed`; verify `processed_tle` rows and `orbit_type` values in DB

---

## Phase 4: CLI Commands

- [ ] `main.py` — `start-db` (`docker compose up -d`)
- [ ] `main.py` — `stop-db` (`docker compose down`)
- [ ] `main.py` — `migrate` (`alembic upgrade head`)
- [ ] `main.py` — `ingest` (calls `ingest_satellites`)
- [ ] `main.py` — `backfill` (calls `ingest_satellites` 7× with backdated `fetched_at` values)
- [ ] `main.py` — `process` (calls `process_unprocessed`)
- [ ] `main.py` — `run-django` (starts Django dev server on configured host/port)
- [ ] `main.py` — `run-litestar` (starts Litestar dev server on configured host/port)
- [ ] End-to-end smoke test: `start-db` → `migrate` → `ingest` → `process` — all exit cleanly

---

## Phase 5: Django REST API

- [ ] `django_api/config/settings.py` — minimal config: `DATABASES = {}`, DRF in `INSTALLED_APPS`, `ROOT_URLCONF`
- [ ] `django_api/manage.py` — standard Django management entry point
- [ ] `django_api/config/urls.py` — root URL conf delegating to `api/v1/`
- [ ] `django_api/satellites/urls.py` — three URL patterns for list, detail, and history
- [ ] `django_api/satellites/serializers.py` — `SatelliteListSerializer`, `SatelliteDetailSerializer`, `TleRecordSerializer` (plain `Serializer`, not `ModelSerializer`)
- [ ] `django_api/satellites/views.py` — `SatelliteListView` with `orbit_type` filter and manual `page`/`page_size` pagination
- [ ] `django_api/satellites/views.py` — `SatelliteDetailView` with 404 on unknown `norad_id`
- [ ] `django_api/satellites/views.py` — `SatelliteHistoryView` with `from_date`/`to_date` filters and pagination
- [ ] Manual test: `run-django`, hit all three endpoints with `curl` or HTTPie; verify response shapes match spec

---

## Phase 6: Litestar REST API

- [ ] `litestar_api/satellites/schemas.py` — five Pydantic schemas: `SatelliteListItem`, `SatelliteListResponse`, `SatelliteDetail`, `TleHistoryItem`, `TleHistoryResponse` (all with `from_attributes=True`)
- [ ] `litestar_api/satellites/controllers.py` — `SatelliteController` with `@get` handlers for list, detail, and history
- [ ] `litestar_api/app.py` — `Litestar` app factory with `SQLAlchemyPlugin`
- [ ] Manual test: `run-litestar`, hit all three endpoints; verify OpenAPI docs load at `/schema`

---

## Phase 7: Testing

- [ ] `tests/conftest.py` — `test_db` session fixture (SQLite in-memory + Alembic migrations applied at session scope)
- [ ] `tests/conftest.py` — `db_session` per-test fixture (function scope, rolls back after each test)
- [ ] `tests/conftest.py` — `factory-boy` factories: `SatelliteFactory`, `TleRecordFactory`, `ProcessedTleFactory`
- [ ] `tests/conftest.py` — `mock_tle_api` fixture using `respx` to mock `/api/tle/25544` and `/api/tle/33591`
- [ ] `tests/test_ingestion.py` — happy path test
- [ ] `tests/test_ingestion.py` — deduplication test
- [ ] `tests/test_ingestion.py` — retry logic test
- [ ] `tests/test_ingestion.py` — partial failure test
- [ ] `tests/test_processing.py` — ISS orbital calculations within tolerance (±1.0 km, ±0.01 min)
- [ ] `tests/test_processing.py` — orbit classification for LEO, MEO, GEO, HEO, OTHER
- [ ] `tests/test_processing.py` — idempotency (no duplicate `processed_tle` rows on second run)
- [ ] `tests/test_django_api.py` — `GET /api/v1/satellites/` returns 200 with paginated results
- [ ] `tests/test_django_api.py` — `?orbit_type=LEO` filter returns only LEO satellites
- [ ] `tests/test_django_api.py` — `?page_size=101` returns 400
- [ ] `tests/test_django_api.py` — `GET /api/v1/satellites/{norad_id}/` returns 200 for existing satellite
- [ ] `tests/test_django_api.py` — `GET /api/v1/satellites/99999/` returns 404
- [ ] `tests/test_django_api.py` — history endpoint returns records ordered by epoch descending
- [ ] `tests/test_django_api.py` — history `from_date`/`to_date` filters return correct range
- [ ] `tests/test_litestar_api.py` — same 7 test cases as Django, using Litestar `TestClient`
- [ ] Run full suite: `pytest -v` — 0 failures

---

## Phase 8: Final Verification

- [ ] Full pipeline run: `start-db` → `migrate` → `backfill` → `process`
- [ ] Both servers running simultaneously: Django on `:8000`, Litestar on `:8001`
- [ ] Manually verify identical JSON responses from both frameworks for all three endpoints
- [ ] `pytest -v` passes with all tests green
- [ ] `stop-db` — clean teardown
