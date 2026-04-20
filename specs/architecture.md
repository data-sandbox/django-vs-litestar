# Satellite TLE Processing Pipeline - Architecture Specification

## Directory Structure

```
django-vs-litestar/
├── main.py                        # Click CLI entry point
├── pyproject.toml
├── docker-compose.yml             # PostgreSQL only
├── alembic.ini
├── .env.example
├── core/                          # Shared logic (no framework dependency)
│   ├── __init__.py
│   ├── models.py                  # SQLAlchemy ORM models (schema source of truth)
│   ├── database.py                # Engine and session factory
│   ├── ingestion.py               # TLE API client and ingest logic
│   ├── processing.py              # sgp4-based orbital calculations
│   └── logging_config.py         # Structured JSON logging setup
├── alembic/
│   ├── env.py
│   └── versions/
├── django_api/
│   ├── manage.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   └── urls.py
│   └── satellites/
│       ├── __init__.py
│       ├── views.py               # DRF APIView classes
│       ├── serializers.py         # DRF serializers
│       └── urls.py
├── litestar_api/
│   ├── app.py                     # Litestar app factory
│   └── satellites/
│       ├── __init__.py
│       ├── controllers.py         # Litestar Controller class
│       └── schemas.py             # Pydantic response DTOs
└── tests/
    ├── conftest.py                # Shared fixtures and test DB setup
    ├── test_ingestion.py
    ├── test_processing.py
    ├── test_django_api.py
    └── test_litestar_api.py
```

---

## Data Layer Strategy

- **Schema source of truth**: SQLAlchemy ORM models in `core/models.py`; no Django ORM models exist
- **Migrations**: Alembic (`alembic upgrade head`); no Django `migrate` command is used
- **Database access**: both Django and Litestar call `core.database.get_session()` — a context-managed SQLAlchemy `Session` factory
- **Django**: used strictly for routing, WSGI entry point, and DRF serialization/view layer; its ORM is disabled via `DATABASES = {}`
- **Litestar**: uses `litestar.contrib.sqlalchemy.plugins.SQLAlchemyPlugin` for session lifecycle management with native dependency injection

---

## Data Model

### Table: `satellites`

| Column       | Type                     | Constraints             |
|--------------|--------------------------|-------------------------|
| `id`         | integer                  | PK, auto-increment      |
| `norad_id`   | integer                  | NOT NULL, UNIQUE        |
| `name`       | varchar(255)             | NOT NULL                |
| `created_at` | timestamp with time zone | NOT NULL, default now() |
| `updated_at` | timestamp with time zone | NOT NULL, default now() |

### Table: `tle_records`

| Column         | Type                     | Constraints                      |
|----------------|--------------------------|----------------------------------|
| `id`           | integer                  | PK, auto-increment               |
| `satellite_id` | integer                  | FK → satellites.id, NOT NULL     |
| `tle_line1`    | varchar(69)              | NOT NULL                         |
| `tle_line2`    | varchar(69)              | NOT NULL                         |
| `epoch`        | timestamp with time zone | NOT NULL                         |
| `fetched_at`   | timestamp with time zone | NOT NULL                         |
|                |                          | UNIQUE (satellite_id, epoch)     |

### Table: `processed_tle`

| Column                    | Type                     | Constraints                           |
|---------------------------|--------------------------|---------------------------------------|
| `id`                      | integer                  | PK, auto-increment                    |
| `tle_record_id`           | integer                  | FK → tle_records.id, NOT NULL, UNIQUE |
| `period_minutes`          | float                    | NOT NULL                              |
| `apogee_km`               | float                    | NOT NULL                              |
| `perigee_km`              | float                    | NOT NULL                              |
| `inclination_deg`         | float                    | NOT NULL                              |
| `eccentricity`            | float                    | NOT NULL                              |
| `mean_motion_rev_per_day` | float                    | NOT NULL                              |
| `orbit_type`              | varchar(10)              | NOT NULL — LEO, MEO, GEO, HEO, OTHER  |
| `processed_at`            | timestamp with time zone | NOT NULL, default now()               |

### Database Indexes

| Table          | Index name                         | Type   | Purpose                          |
|----------------|------------------------------------|--------|----------------------------------|
| `satellites`   | `ix_satellites_norad_id`           | UNIQUE | Fast lookup by NORAD ID          |
| `tle_records`  | `uq_tle_records_satellite_epoch`   | UNIQUE | Deduplication constraint         |
| `tle_records`  | `ix_tle_records_satellite_id`      | BTREE  | FK join performance              |
| `tle_records`  | `ix_tle_records_epoch`             | BTREE  | Date-range filtering on history  |
| `processed_tle`| `uq_processed_tle_tle_record_id`   | UNIQUE | One processed row per TLE record |

---

## Module Responsibilities

### `core/logging_config.py`

- Exports `setup_logging(level: str = "INFO") -> None`
- Configures the root logger with `python-json-logger`'s `JsonFormatter`
- Log format includes: `timestamp`, `level`, `logger`, `message` plus any extra kwargs passed to the logger
- Called once at CLI startup before any other operation
- All other modules use `logging.getLogger(__name__)` — no direct formatter references elsewhere

### `core/models.py`

- Defines `Base = DeclarativeBase()`, imported by `alembic/env.py` for autogenerate support
- `Satellite`: maps to `satellites` table; `relationship("TleRecord", back_populates="satellite")`
- `TleRecord`: maps to `tle_records`; FK to `Satellite`; `UniqueConstraint("satellite_id", "epoch")`; `relationship("ProcessedTle", uselist=False, back_populates="tle_record")`
- `ProcessedTle`: maps to `processed_tle`; FK to `TleRecord`; `UniqueConstraint("tle_record_id")`

### `core/database.py`

- Reads `DATABASE_URL` from environment at import time
- Creates a module-level `engine = create_engine(DATABASE_URL, pool_pre_ping=True)`
- Creates `SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)`
- Exports `get_session()` as a `contextlib.contextmanager` that yields a `Session`, commits on clean exit, rolls back on exception:

```python
@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### `core/ingestion.py`

- Defines a module-level constant:
  ```python
  SATELLITE_TARGETS: list[tuple[str, int]] = [
      ("ISS (ZARYA)", 25544),
      ("NOAA 19", 33591),
  ]
  ```
- `fetch_tle(norad_id: int, client: httpx.Client) -> dict`: calls `GET /api/tle/{norad_id}`, retries up to 3x with exponential backoff (1s → 2s → 4s) on any non-2xx response; raises after exhausting retries
- `ingest_satellites(session: Session, fetched_at: datetime | None = None) -> dict`: iterates `SATELLITE_TARGETS`, calls `fetch_tle` for each, upserts `Satellite` rows, inserts `TleRecord` rows (skipping on unique constraint violation), returns `{"fetched": n, "inserted": n, "skipped": n}`
- Uses `httpx.Client` (synchronous) — batch pipeline work does not benefit from async overhead
- The `fetched_at` parameter enables the backfill command to pass backdated timestamps without duplicating logic

### `core/processing.py`

- `compute_orbital_params(tle_line1: str, tle_line2: str) -> dict`: uses `sgp4.api.Satrec.twoline2rv()` to parse the TLE; derives all six orbital fields from the parsed Satrec object (see requirements for formulas)
- `classify_orbit(apogee_km: float, perigee_km: float, eccentricity: float) -> str`: pure function; returns one of `LEO | MEO | GEO | HEO | OTHER` per the orbit classification table in the requirements
- `process_unprocessed(session: Session) -> dict`: queries all `TleRecord` rows that have no matching `ProcessedTle` row (LEFT JOIN / NOT EXISTS); calls `compute_orbital_params` + `classify_orbit` for each; bulk-inserts `ProcessedTle` rows; returns `{"processed": n, "errors": n}`

---

## Framework Design

### Django REST API

#### Settings (`django_api/config/settings.py`)

```python
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_api.satellites",
]

DATABASES = {}          # Django ORM disabled; all DB access goes through SQLAlchemy
ROOT_URLCONF = "django_api.config.urls"
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
```

- No `django.contrib.auth`, no `django.contrib.admin` — minimal install only
- `DATABASES = {}` prevents Django from attempting any ORM connections or migrations

#### Session Injection Pattern

DRF `APIView` methods call `core.database.get_session()` directly as a context manager inside each handler. Session lifetime is scoped to the request method body:

```python
class SatelliteListView(APIView):
    def get(self, request):
        with get_session() as session:
            rows = session.execute(...).all()
        serializer = SatelliteListSerializer(rows, many=True)
        return Response(serializer.data)
```

No DRF middleware or dependency injection framework is used for the session.

#### URL Routing

`django_api/config/urls.py`:
```python
urlpatterns = [
    path("api/v1/", include("django_api.satellites.urls")),
]
```

`django_api/satellites/urls.py`:
```python
urlpatterns = [
    path("satellites/", SatelliteListView.as_view()),
    path("satellites/<int:norad_id>/", SatelliteDetailView.as_view()),
    path("satellites/<int:norad_id>/history/", SatelliteHistoryView.as_view()),
]
```

#### DRF Serializers and Views

Three `APIView` subclasses, one per endpoint:

| View class             | Serializer                  | Endpoint                        |
|------------------------|-----------------------------|---------------------------------|
| `SatelliteListView`    | `SatelliteListSerializer`   | `GET /api/v1/satellites/`       |
| `SatelliteDetailView`  | `SatelliteDetailSerializer` | `GET /api/v1/satellites/{id}/`  |
| `SatelliteHistoryView` | `TleRecordSerializer`       | `GET /api/v1/satellites/{id}/history/` |

All serializers are `Serializer` subclasses (not `ModelSerializer`) because the source data is SQLAlchemy row objects, not Django model instances.

Pagination is implemented manually: each view reads `page` and `page_size` from `request.query_params`, applies `OFFSET`/`LIMIT` in the SQLAlchemy query, and constructs `next`/`previous` URL strings. DRF's `PageNumberPagination` is not used because it assumes Django ORM querysets.

---

### Litestar REST API

#### App Factory (`litestar_api/app.py`)

```python
from litestar import Litestar
from litestar.contrib.sqlalchemy.plugins import SQLAlchemyPlugin, SQLAlchemySyncConfig

app = Litestar(
    route_handlers=[SatelliteController],
    plugins=[
        SQLAlchemyPlugin(
            config=SQLAlchemySyncConfig(connection_string=settings.DATABASE_URL)
        )
    ],
)
```

The `SQLAlchemyPlugin` manages session lifecycle and injects a `Session` into any handler that declares it as a typed parameter.

#### Session Injection Pattern

Litestar handlers declare `db: Session` as a parameter; the `SQLAlchemyPlugin` resolves and injects it automatically — no explicit `get_session()` context manager calls inside handlers:

```python
class SatelliteController(Controller):
    path = "/api/v1/satellites"

    @get("")
    def list_satellites(self, db: Session, orbit_type: str | None = None,
                        page: int = 1, page_size: int = 20) -> SatelliteListResponse:
        rows = db.execute(...).all()
        ...
```

Session commit/rollback is handled by the plugin's middleware layer.

#### Controller and Schema Pattern

`litestar_api/satellites/controllers.py` — a single `Controller` subclass with three `@get` route handler methods.

`litestar_api/satellites/schemas.py` — Pydantic `BaseModel` subclasses used as return type annotations, enabling Litestar's automatic OpenAPI generation and response serialization:

| Schema                  | Used as return type of                  |
|-------------------------|-----------------------------------------|
| `SatelliteListItem`     | element within `SatelliteListResponse`  |
| `SatelliteListResponse` | `GET /satellites/`                      |
| `SatelliteDetail`       | `GET /satellites/{norad_id}/`           |
| `TleHistoryItem`        | element within `TleHistoryResponse`     |
| `TleHistoryResponse`    | `GET /satellites/{norad_id}/history/`   |

All schemas include `model_config = ConfigDict(from_attributes=True)` to support construction from SQLAlchemy row objects.

The auto-generated OpenAPI docs are accessible at `/schema` when the Litestar server is running — a built-in capability not present in Django without third-party packages.

---

## Infrastructure

### Docker Compose (`docker-compose.yml`)

The only containerized service is PostgreSQL. Django and Litestar run as local processes.

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: satellite_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single ORM | SQLAlchemy for both frameworks | Eliminates duplicate model definitions; Alembic owns all migrations; both APIs stay in sync automatically |
| Django ORM disabled | `DATABASES = {}` | Prevents unintended ORM interference and makes the architectural boundary explicit |
| Sync HTTP client | `httpx.Client` (not `AsyncClient`) | Pipeline runs as CLI batch work; async adds complexity with no throughput benefit for two sequential fetches |
| Fixed satellite targets | Hardcoded NORAD IDs 25544 and 33591 | Keeps data volume minimal for a focused demo while using real-world satellites (ISS = LEO, NOAA 19 = LEO/polar — good test cases) |
| Manual pagination in Django | `OFFSET`/`LIMIT` in view method | DRF's `PageNumberPagination` requires Django ORM querysets; manual implementation works cleanly with SQLAlchemy |
| Native DI in Litestar | `SQLAlchemyPlugin` | Demonstrates Litestar's first-class dependency injection vs. Django's more imperative style — a central framework comparison point |
| Backfill via `fetched_at` override | Single `ingest_satellites` function with optional param | Avoids a separate code path; the unique constraint on `(satellite_id, epoch)` naturally handles deduplication across runs |
