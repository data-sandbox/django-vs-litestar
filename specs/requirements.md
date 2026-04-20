# Satellite TLE Processing Pipeline - Requirements Specification

## Overview

Build a satellite TLE (Two-Line Element) data pipeline with a REST API comparison between Django and Litestar frameworks.

The system:
1. Fetches satellite TLE data from `https://tle.ivanstanojevic.me/`
2. Stores raw and processed records in a PostgreSQL database (run via Docker Compose)
3. Simulates 7-day historical data via backfill
4. Exposes identical read-only REST API endpoints implemented in both Django (DRF) and Litestar for side-by-side comparison

**Framework comparison goal:** Both APIs expose the same endpoints and return the same response shapes. The comparison highlights differences in routing, serialization, dependency injection, and developer ergonomics between the two frameworks.

---

## Demo & Documentation

The primary deliverable for this project is a `README.md` intended to be read on GitHub by other developers evaluating Django vs Litestar.

### README Structure

The README combines two angles:

1. **Quick start** — readers can clone, start the database, run backfill + process, and hit both servers. `curl` examples confirm identical JSON from both ports.

2. **Side-by-side code comparisons** — five concrete diffs showing how each framework handles the same concern:
   - Routing registration
   - Serialization / response schema declaration
   - Database session injection
   - 404 error handling
   - Query parameter validation

### Placeholders in README.md

The following items in `README.md` require updates once the relevant phases are complete:

| Placeholder | Required by | Condition |
|---|---|---|
| GitHub repo URL in clone command | Phase 0 | Repo pushed to GitHub |
| Screenshot: `migrate` terminal output | Phase 4 | CLI implemented |
| Screenshot: structured log output from `backfill` + `process` | Phase 4 | CLI implemented |
| Screenshot: side-by-side curl responses | Phase 5–6 | Both APIs running |
| Screenshot: Django Swagger UI (`/api/schema/swagger-ui/`) | Phase 5 | Django API + drf-spectacular |
| Screenshot: Litestar Swagger UI (`/schema/swagger`) | Phase 6 | Litestar API running |
| Screenshot: `pytest -v` all-green output | Phase 7 | Test suite complete |
| Code examples in comparison section | Phase 5–6 | Verify against actual implementation |

### Summary Table (README target)

The README ends with a scored table across: routing boilerplate, type safety, built-in OpenAPI, query param validation, and session injection ergonomics.

---

## Functional Requirements

### 1. Data Ingestion

- Fetch TLE data for exactly two satellites by NORAD ID:
  - **ISS (ZARYA)** — NORAD ID `25544` → `GET https://tle.ivanstanojevic.me/api/tle/25544`
  - **NOAA 19** — NORAD ID `33591` → `GET https://tle.ivanstanojevic.me/api/tle/33591`
- For each response, extract: satellite name, NORAD ID, TLE line 1, TLE line 2, epoch date
- Upsert `satellites` rows by `norad_id` (insert if new, update `name` and `updated_at` if changed)
- Insert new `tle_records` rows; skip duplicates based on `(satellite_id, epoch)` unique constraint
- Record `fetched_at` as the current UTC timestamp for each fetch
- Handle API failures gracefully: retry up to 3 times with exponential backoff (1s, 2s, 4s)
- Log a structured summary on completion: total fetched, inserted, skipped

### 2. Backfill

- Simulate 7-day history by running the ingest operation 7 times, with `fetched_at` backdated by 1 day per iteration (i.e., day 0 = today, day 1 = yesterday, ..., day 6 = 6 days ago)
- Because the upstream API only provides current TLE data, each run produces the same TLE content but different `fetched_at` values — this is sufficient to populate the history table for development and testing purposes
- After all 7 ingest runs, skip any `tle_records` that were already inserted (deduplication via unique constraint on `(satellite_id, epoch)`)
- Log per-day progress

### 3. Processing

For each `tle_record` that does not yet have a corresponding `processed_tle` row:

**Calculations** (use the `sgp4` library to propagate the TLE):

- **Period (minutes)**: `1440.0 / mean_motion` where `mean_motion` is in revolutions/day (from TLE line 2, field 8)
- **Semi-major axis (km)**: `a = (μ / n²)^(1/3)` where μ = 398600.4418 km³/s², n = mean_motion in rad/s
- **Apogee altitude (km)**: `a × (1 + e) − 6371.0`
- **Perigee altitude (km)**: `a × (1 − e) − 6371.0`
- **Inclination (degrees)**: directly from TLE line 2, field 3
- **Eccentricity**: directly from TLE line 2, field 5 (implied decimal)
- **Mean motion (rev/day)**: directly from TLE line 2, field 8

**Orbit classification** (based on mean perigee/apogee):

| Orbit Type | Condition                                                       |
|------------|-----------------------------------------------------------------|
| `HEO`      | eccentricity > 0.25                                             |
| `GEO`      | 35,586 km ≤ apogee_km ≤ 35,986 km AND eccentricity ≤ 0.25     |
| `MEO`      | 2,000 km ≤ perigee_km < 35,586 km AND orbit is not GEO or HEO |
| `LEO`      | perigee_km < 2,000 km AND eccentricity ≤ 0.25                  |
| `OTHER`    | anything that does not match the above                          |

- Store one `processed_tle` row per `tle_record`
- Log count of records processed per run

### 4. REST API Endpoints

Both the Django and Litestar implementations expose the same three endpoints under `/api/v1/`. Both servers run locally (not in Docker). Django defaults to port `8000`; Litestar defaults to port `8001`.

---

#### `GET /api/v1/satellites/`

List all satellites with their latest processed orbital data.

**Query parameters:**

| Parameter   | Type    | Required | Default | Constraints          |
|-------------|---------|----------|---------|----------------------|
| `orbit_type`| string  | No       | —       | One of: LEO, MEO, GEO, HEO, OTHER |
| `page`      | integer | No       | 1       | ≥ 1                  |
| `page_size` | integer | No       | 20      | 1–100                |

**Response `200 OK`:**

```json
{
  "count": 150,
  "next": "/api/v1/satellites/?page=2&page_size=20",
  "previous": null,
  "results": [
    {
      "norad_id": 25544,
      "name": "ISS (ZARYA)",
      "orbit_type": "LEO",
      "period_minutes": 92.68,
      "apogee_km": 418.5,
      "perigee_km": 409.2,
      "inclination_deg": 51.64,
      "last_updated": "2026-04-18T12:00:00Z"
    }
  ]
}
```

- `last_updated` is the `epoch` of the satellite's most recent `tle_record`
- Satellites with no `processed_tle` record are excluded from results
- Results are ordered by `norad_id` ascending

---

#### `GET /api/v1/satellites/{norad_id}/`

Get full details for a single satellite including the latest processed orbital parameters.

**Path parameters:**

| Parameter  | Type    | Description       |
|------------|---------|-------------------|
| `norad_id` | integer | NORAD catalog ID  |

**Response `200 OK`:**

```json
{
  "norad_id": 25544,
  "name": "ISS (ZARYA)",
  "orbit_type": "LEO",
  "period_minutes": 92.68,
  "apogee_km": 418.5,
  "perigee_km": 409.2,
  "inclination_deg": 51.64,
  "eccentricity": 0.0006703,
  "mean_motion_rev_per_day": 15.53,
  "last_updated": "2026-04-18T12:00:00Z"
}
```

**Response `404 Not Found`:**

```json
{
  "detail": "Satellite with NORAD ID 99999 not found."
}
```

---

#### `GET /api/v1/satellites/{norad_id}/history/`

Get paginated TLE history for a satellite.

**Path parameters:**

| Parameter  | Type    | Description       |
|------------|---------|-------------------|
| `norad_id` | integer | NORAD catalog ID  |

**Query parameters:**

| Parameter   | Type    | Required | Default | Format              |
|-------------|---------|----------|---------|---------------------|
| `page`      | integer | No       | 1       | ≥ 1                 |
| `page_size` | integer | No       | 20      | 1–100               |
| `from_date` | string  | No       | —       | ISO 8601 date (UTC) |
| `to_date`   | string  | No       | —       | ISO 8601 date (UTC) |

**Response `200 OK`:**

```json
{
  "count": 7,
  "next": null,
  "previous": null,
  "results": [
    {
      "tle_line1": "1 25544U 98067A   26108.50000000  .00001234  00000-0  12345-4 0  9995",
      "tle_line2": "2 25544  51.6416 100.0000 0006703  92.0000 268.0000 15.53000000000000",
      "epoch": "2026-04-18T12:00:00Z",
      "fetched_at": "2026-04-18T14:30:00Z"
    }
  ]
}
```

- Results are ordered by `epoch` descending (most recent first)
- Returns `404` if the `norad_id` does not exist

---

### 5. Management Commands (CLI)

Entry point: `main.py` using the `click` library. All commands read configuration from environment variables (with `.env` file support via `python-dotenv`).

| Command         | Description                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| `start-db`      | Run `docker compose up -d` to start the PostgreSQL container                |
| `stop-db`       | Run `docker compose down` to stop the PostgreSQL container                  |
| `migrate`       | Run Alembic migrations to create/update the database schema                 |
| `ingest`        | Fetch and store the latest TLE data from the upstream API                   |
| `backfill`      | Simulate 7-day history (runs ingest 7x with backdated `fetched_at`)         |
| `process`       | Compute and store orbital parameters for all unprocessed `tle_records`      |
| `run-django`    | Start the Django development server (default: `127.0.0.1:8000`)             |
| `run-litestar`  | Start the Litestar development server (default: `127.0.0.1:8001`)           |

All commands log to stdout using structured JSON format.

### 6. Logging

- Use `python-json-logger` for structured JSON log output
- Configure logging in `core/logging_config.py` and call `setup_logging()` at CLI startup
- Log level controlled by `LOG_LEVEL` env var (default: `INFO`)
- Every log record must include: `timestamp`, `level`, `logger`, `message`
- Ingestion logs must also include: `page`, `fetched`, `inserted`, `skipped`
- Processing logs must also include: `processed`, `errors`
- HTTP errors from the upstream API must be logged at `WARNING` level including `status_code` and `url`

---

## Configuration

All configuration via environment variables. Provide a `.env.example` file.

| Variable            | Default                                 | Description                                   |
|---------------------|-----------------------------------------|-----------------------------------------------|
| `DATABASE_URL`      | `postgresql://postgres:postgres@localhost:5432/satellite_db` | SQLAlchemy-compatible connection string |
| `TLE_API_BASE_URL`  | `https://tle.ivanstanojevic.me`         | Base URL for the TLE API                      |
| `BACKFILL_DAYS`     | `7`                                     | Number of historical days to simulate         |
| `DJANGO_HOST`       | `127.0.0.1`                             | Host for the Django dev server                |
| `DJANGO_PORT`       | `8000`                                  | Port for the Django dev server                |
| `LITESTAR_HOST`     | `127.0.0.1`                             | Host for the Litestar dev server              |
| `LITESTAR_PORT`     | `8001`                                  | Port for the Litestar dev server              |
| `LOG_LEVEL`         | `INFO`                                  | Logging level (DEBUG, INFO, WARNING, ERROR)   |

---

## Dependencies

Update `pyproject.toml` with the following:

**Runtime:**

| Package              | Purpose                                          |
|----------------------|--------------------------------------------------|
| `click`              | CLI entry point                                  |
| `python-dotenv`      | `.env` file loading                              |
| `sqlalchemy`         | Shared ORM and DB access layer                   |
| `alembic`            | Database migrations                              |
| `psycopg2-binary`    | PostgreSQL driver                                |
| `sgp4`               | TLE parsing and orbital propagation              |
| `httpx`              | Async-capable HTTP client for TLE API calls      |
| `python-json-logger` | Structured JSON logging                          |
| `django`             | Web framework (routing, middleware, DRF)         |
| `djangorestframework`| DRF serializers and API views                    |
| `litestar`           | Web framework with native SQLAlchemy integration |

**Development:**

| Package           | Purpose                                               |
|-------------------|-------------------------------------------------------|
| `pytest`          | Test runner                                           |
| `pytest-django`   | Django test fixtures and `django_db` marker           |
| `pytest-asyncio`  | Async test support for Litestar                       |
| `respx`           | Mock `httpx` requests in tests                        |
| `factory-boy`     | Test data factories for `satellites` and `tle_records`|

---

## Testing Requirements

### Setup

- `tests/conftest.py` provides:
  - A `test_db` fixture that creates a fresh in-memory SQLite database (or a temporary PostgreSQL schema) for each test session and applies Alembic migrations
  - A `db_session` fixture scoped to each test function
  - SQLAlchemy model factories via `factory-boy` for `Satellite`, `TleRecord`, and `ProcessedTle`
  - A `mock_tle_api` fixture using `respx` that mocks the two individual NORAD ID endpoints (`/api/tle/25544` and `/api/tle/33591`) with fixed response payloads for ISS (ZARYA) and NOAA 19

### Test Files

**`test_ingestion.py`**
- Happy path: fetching mocked responses for both NORAD IDs inserts 2 `satellites` and 2 `tle_records`
- Deduplication: running ingest twice does not create duplicate `tle_records` (unique constraint on `satellite_id, epoch`)
- Retry logic: the client retries on HTTP 500 up to 3 times before raising
- Partial failure: if one satellite fetch fails after all retries, the other satellite is still processed and inserted

**`test_processing.py`**
- Orbital calculations: verify `period_minutes`, `apogee_km`, `perigee_km` for a known TLE (e.g., ISS) against expected values within ±1.0 km / ±0.01 min tolerance
- Orbit classification: assert correct `orbit_type` for one representative TLE from each category (LEO, MEO, GEO, HEO, OTHER)
- Idempotency: running `process` twice on the same records does not create duplicate `processed_tle` rows

**`test_django_api.py`**
- `GET /api/v1/satellites/` returns `200` with paginated results
- `GET /api/v1/satellites/?orbit_type=LEO` filters correctly
- `GET /api/v1/satellites/?page_size=101` returns `400`
- `GET /api/v1/satellites/{norad_id}/` returns `200` for an existing satellite
- `GET /api/v1/satellites/99999/` returns `404`
- `GET /api/v1/satellites/{norad_id}/history/` returns `200` with TLE records ordered by epoch descending
- `GET /api/v1/satellites/{norad_id}/history/?from_date=2026-04-15&to_date=2026-04-17` returns only records in that date range

**`test_litestar_api.py`**
- Same test cases as `test_django_api.py`, exercising the Litestar implementation
- Use Litestar's built-in `TestClient`
