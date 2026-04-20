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

- [x] `core/processing.py` — `compute_orbital_params(tle_line1, tle_line2)` using `sgp4`
- [x] `core/processing.py` — `classify_orbit(apogee_km, perigee_km, eccentricity)` classification logic
- [x] `core/processing.py` — `process_unprocessed(session)` batch processor
- [x] Smoke test: call `process_unprocessed`; verify `processed_tle` rows and `orbit_type` values in DB

---

## Phase 4: CLI Commands

- [x] `main.py` — `start-db` (`docker compose up -d`)
- [x] `main.py` — `stop-db` (`docker compose down`)
- [x] `main.py` — `migrate` (`alembic upgrade head`)
- [x] `main.py` — `ingest` (calls `ingest_satellites`)
- [x] `main.py` — `backfill` (calls `ingest_satellites` 7× with backdated `fetched_at` values)
- [x] `main.py` — `process` (calls `process_unprocessed`)
- [x] `main.py` — `run-django` (starts Django dev server on configured host/port)
- [x] `main.py` — `run-litestar` (starts Litestar dev server on configured host/port)
- [x] End-to-end smoke test: `start-db` → `migrate` → `ingest` → `process` — all exit cleanly

---

## Phase 5: Django REST API

- [x] `django_api/config/settings.py` — minimal config: `DATABASES = {}`, DRF in `INSTALLED_APPS`, `ROOT_URLCONF`
- [x] `django_api/manage.py` — standard Django management entry point
- [x] `django_api/config/urls.py` — root URL conf delegating to `api/v1/`
- [x] `django_api/satellites/urls.py` — three URL patterns for list, detail, and history
- [x] `django_api/satellites/serializers.py` — `SatelliteListSerializer`, `SatelliteDetailSerializer`, `TleRecordSerializer` (plain `Serializer`, not `ModelSerializer`)
- [x] `django_api/satellites/views.py` — `SatelliteListView` with `orbit_type` filter and manual `page`/`page_size` pagination
- [x] `django_api/satellites/views.py` — `SatelliteDetailView` with 404 on unknown `norad_id`
- [x] `django_api/satellites/views.py` — `SatelliteHistoryView` with `from_date`/`to_date` filters and pagination
- [ ] Manual test: `run-django`, hit all three endpoints with `curl` or HTTPie; verify response shapes match spec

---

## Phase 6: Litestar REST API

- [x] `litestar_api/satellites/schemas.py` — five Pydantic schemas: `SatelliteListItem`, `SatelliteListResponse`, `SatelliteDetail`, `TleHistoryItem`, `TleHistoryResponse` (all with `from_attributes=True`)
- [x] `litestar_api/satellites/controllers.py` — `SatelliteController` with `@get` handlers for list, detail, and history
- [x] `litestar_api/app.py` — `Litestar` app factory with `Provide(provide_db)` dependency injection
- [ ] Manual test: `run-litestar`, hit all three endpoints; verify OpenAPI docs load at `/schema`

---

## Phase 7: Testing

- [x] `tests/conftest.py` — `pg_container` session fixture (PostgresContainer via testcontainers)
- [x] `tests/conftest.py` — `test_engine` session fixture (creates engine, runs Alembic migrations, patches `core.database`)
- [x] `tests/conftest.py` — `db_session` per-test fixture (function scope, truncates tables after each test)
- [x] `tests/conftest.py` — `factory-boy` factories: `satellite_factory`, `tle_record_factory`, `processed_tle_factory`
- [x] `tests/conftest.py` — `make_patch_get_session` helper for monkeypatching views
- [x] `tests/test_processing.py` — ISS orbital calculations within tolerance
- [x] `tests/test_processing.py` — orbit classification for LEO, MEO, GEO, HEO, OTHER
- [x] `tests/test_processing.py` — idempotency (no duplicate `processed_tle` rows on second run)
- [x] `tests/test_processing.py` — multi-satellite batch processing
- [x] `tests/test_django_api.py` — `GET /api/v1/satellites/` returns 200 with paginated results
- [x] `tests/test_django_api.py` — `?orbit_type=MEO` filter returns only MEO satellites
- [x] `tests/test_django_api.py` — `?orbit_type=INVALID` returns 400
- [x] `tests/test_django_api.py` — pagination with `page_size=1` returns `next` link
- [x] `tests/test_django_api.py` — `GET /api/v1/satellites/{norad_id}/` returns 200 for existing satellite
- [x] `tests/test_django_api.py` — `GET /api/v1/satellites/99999/` returns 404
- [x] `tests/test_django_api.py` — history endpoint returns records with correct TLE data
- [x] `tests/test_django_api.py` — history 404 for unknown satellite
- [x] `tests/test_litestar_api.py` — same 9 test cases as Django, using Litestar `TestClient`
- [x] Run full suite: `pytest -q` — 38 passed, 0 failures

---

## Phase 8: Final Verification

- [ ] Full pipeline run: `start-db` → `migrate` → `backfill` → `process`
- [ ] Both servers running simultaneously: Django on `:8000`, Litestar on `:8001`
- [ ] Manually verify identical JSON responses from both frameworks for all three endpoints
- [ ] `pytest -v` passes with all tests green
- [ ] `stop-db` — clean teardown
