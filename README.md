# Django vs Litestar API Comparison

The project creates a satellite TLE pipeline implemented twice — once with **Django REST Framework**, once with **Litestar** — sharing a single SQLAlchemy data layer. It fetches live Two-Line Element (TLE) orbital data for the ISS and NOAA 19, processes it with `sgp4` to compute apogee, perigee, period, and orbit type, then serves the results through identical REST API endpoints in both frameworks. The goal is a concrete, side-by-side comparison of how each framework handles routing, serialization, dependency injection, and error handling.

---

## Quick Start

### Prerequisites

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker

### 1 — Start the database

Clone this repo then run:

```bash
cp .env.example .env
uv sync
uv run python main.py start-db
uv run python main.py migrate
```

### 2 — Populate data

```bash
uv run python main.py backfill   # fetches live TLE data, simulates 7 days of history
uv run python main.py process    # computes orbital parameters for all new TLE records
```

Expected log output (structured JSON):
```json
{"timestamp": "2026-04-20T...", "level": "INFO", "event": "ingest complete", "fetched": 2, "inserted": 2, "skipped": 0}
{"timestamp": "2026-04-20T...", "level": "INFO", "event": "process complete", "processed": 2, "errors": 0}
```

### 3 — Run both APIs

In two separate terminals:

```bash
uv run python main.py run-django     # http://localhost:8000
uv run python main.py run-litestar   # http://localhost:8001
```

Both servers read from the same PostgreSQL tables. The same request to either port returns the same JSON:

```bash
curl http://localhost:8000/api/v1/satellites/        # Django
curl http://localhost:8001/api/v1/satellites/        # Litestar
```


---

## The Pipeline

```
tle.ivanstanojevic.me
    │
    │  GET /api/tle/25544  (ISS)
    │  GET /api/tle/33591  (NOAA 19)
    ▼
core/ingestion.py          — httpx, retry + backoff, ON CONFLICT DO NOTHING
    │
    ▼
PostgreSQL: tle_records    — raw TLE lines + epoch timestamp
    │
    ▼
core/processing.py         — sgp4 propagation, orbit classification (LEO/MEO/GEO/HEO)
    │
    ▼
PostgreSQL: processed_tle  — apogee, perigee, period, orbit_type
    │
    ├──▶  django_api/   (port 8000)   DRF APIView + plain Serializer
    └──▶  litestar_api/ (port 8001)   Litestar Controller + Pydantic schemas
```

Both framework layers are read-only. All writes happen through `core/`.

---

## API Endpoints

All three endpoints are available on both ports with identical request/response shapes.

| Endpoint | Description |
|---|---|
| `GET /api/v1/satellites/` | List all satellites with latest orbital data |
| `GET /api/v1/satellites/{norad_id}/` | Single satellite detail |
| `GET /api/v1/satellites/{norad_id}/history/` | Paginated TLE history |

### Example: list satellites

```bash
curl "http://localhost:8000/api/v1/satellites/?orbit_type=LEO&page_size=5"
```

```json
{
  "count": 2,
  "next": null,
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
      "last_updated": "2026-04-19T11:45:32Z"
    },
    {
      "norad_id": 33591,
      "name": "NOAA 19",
      "orbit_type": "LEO",
      "period_minutes": 102.1,
      "apogee_km": 865.3,
      "perigee_km": 849.7,
      "inclination_deg": 99.18,
      "last_updated": "2026-04-15T04:35:03Z"
    }
  ]
}
```



### Example: 404 response

```bash
curl "http://localhost:8000/api/v1/satellites/99999/"
```

```json
{"detail": "Satellite with NORAD ID 99999 not found."}
```

---

## Framework Comparison

Both implementations live in the same repository and share a single data layer (`core/`). The differences below are purely about what each framework requires to expose the same endpoint.

---

### 1. Routing

**Django** — URLs are registered in two separate files. Each class must be explicitly wired with `.as_view()`:

```python
# django_api/config/urls.py
urlpatterns = [
    path("api/v1/", include("django_api.satellites.urls")),
]

# django_api/satellites/urls.py
urlpatterns = [
    path("satellites/", SatelliteListView.as_view()),
    path("satellites/<int:norad_id>/", SatelliteDetailView.as_view()),
    path("satellites/<int:norad_id>/history/", SatelliteHistoryView.as_view()),
]
```

**Litestar** — A single `Controller` class. Routes are declared as decorators on methods; the prefix is set once on the class:

```python
# litestar_api/satellites/controllers.py
class SatelliteController(Controller):
    path = "/api/v1/satellites"

    @get("")
    def list_satellites(self, ...) -> SatelliteListResponse: ...

    @get("/{norad_id:int}")
    def get_satellite(self, norad_id: int, ...) -> SatelliteDetail: ...

    @get("/{norad_id:int}/history")
    def get_history(self, norad_id: int, ...) -> TleHistoryResponse: ...
```

---

### 2. Serialization / Response Schemas

**Django** — Serializer classes are defined separately from views. Serializers have no connection to the response type in the view signature; the contract is implicit:

```python
# django_api/satellites/serializers.py
class SatelliteListSerializer(Serializer):
    norad_id       = IntegerField()
    name           = CharField()
    orbit_type     = CharField()
    period_minutes = FloatField()
    apogee_km      = FloatField()
    perigee_km     = FloatField()
    inclination_deg = FloatField()
    last_updated   = DateTimeField()

# django_api/satellites/views.py
class SatelliteListView(APIView):
    def get(self, request):
        ...
        serializer = SatelliteListSerializer(rows, many=True)
        return Response({"count": count, "results": serializer.data, ...})
```

**Litestar** — The return type annotation *is* the schema. Litestar reads it at startup to generate OpenAPI docs and validate responses automatically:

```python
# litestar_api/satellites/schemas.py
class SatelliteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    norad_id:        int
    name:            str
    orbit_type:      str
    period_minutes:  float
    apogee_km:       float
    perigee_km:      float
    inclination_deg: float
    last_updated:    datetime

class SatelliteListResponse(BaseModel):
    count:    int
    next:     str | None
    previous: str | None
    results:  list[SatelliteListItem]

# litestar_api/satellites/controllers.py
    @get("")
    def list_satellites(self, ...) -> SatelliteListResponse:
        ...
```

No separate wiring step. The type annotation drives serialization, validation, and OpenAPI generation in one place.

---

### 3. Dependency Injection (Database Session)

**Django** — No built-in DI system. Sessions are acquired manually as a context manager inside each view method:

```python
class SatelliteListView(APIView):
    def get(self, request):
        with get_session() as session:   # called explicitly in every handler
            rows = session.execute(...).all()
        serializer = SatelliteListSerializer(rows, many=True)
        return Response(...)
```

Every view method repeats this `with get_session()` block. Session lifecycle (commit/rollback) is managed in `core/database.py`.

**Litestar** — A `provide_db` generator is registered at app startup via `Provide`. Litestar resolves `db: Session` from the dependency graph and calls the generator — no `with` block required inside the handler:

```python
# litestar_api/app.py
from collections.abc import Generator
from litestar import Litestar
from litestar.di import Provide
from sqlalchemy.orm import Session
from core.database import get_session

def provide_db() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session            # commit/rollback handled here

app = Litestar(
    route_handlers=[SatelliteController],
    dependencies={"db": Provide(provide_db)},
)

# litestar_api/satellites/controllers.py
class SatelliteController(Controller):
    @get("", sync_to_thread=False)
    def list_satellites(self, db: Session, ...) -> SatelliteListResponse:
        rows = db.execute(...).all()   # db injected automatically
        ...
```

---

### 4. 404 Error Handling

**Django** — Raise DRF's `NotFound` exception; DRF's exception handler serializes it to JSON:

```python
from rest_framework.exceptions import NotFound

class SatelliteDetailView(APIView):
    def get(self, request, norad_id):
        with get_session() as session:
            row = session.execute(...).one_or_none()
        if row is None:
            raise NotFound(detail=f"Satellite with NORAD ID {norad_id} not found.")
        return Response(SatelliteDetailSerializer(row).data)
```

**Litestar** — Raise Litestar's `NotFoundException`; it serializes identically:

```python
from litestar.exceptions import NotFoundException

class SatelliteController(Controller):
    @get("/{norad_id:int}")
    def get_satellite(self, db: Session, norad_id: int) -> SatelliteDetail:
        row = db.execute(...).one_or_none()
        if row is None:
            raise NotFoundException(detail=f"Satellite with NORAD ID {norad_id} not found.")
        return SatelliteDetail.model_validate(row)
```

Both return `{"detail": "..."}` with a `404` status — the same wire format despite different exception classes.

---

### 5. Query Parameter Validation

**Django** — Parameters are read from `request.query_params` and validated manually. DRF provides no declarative query parameter validation:

```python
class SatelliteListView(APIView):
    VALID_ORBIT_TYPES = {"LEO", "MEO", "GEO", "HEO", "OTHER"}

    def get(self, request):
        orbit_type = request.query_params.get("orbit_type")
        if orbit_type and orbit_type not in self.VALID_ORBIT_TYPES:
            return Response({"detail": "Invalid orbit_type."}, status=400)
        try:
            page      = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 20))
        except ValueError:
            return Response({"detail": "page and page_size must be integers."}, status=400)
        if not (1 <= page_size <= 100):
            return Response({"detail": "page_size must be between 1 and 100."}, status=400)
        ...
```

**Litestar** — Parameters are declared in the function signature with type annotations and default values. Litestar parses, coerces, and validates them automatically:

```python
from litestar.params import Parameter

    @get("", sync_to_thread=False)
    def list_satellites(
        self,
        db: Session,
        orbit_type: Literal["LEO", "MEO", "GEO", "HEO", "OTHER"] | None = None,
        page: Annotated[int, Parameter(ge=1)] = 1,
        page_size: Annotated[int, Parameter(ge=1, le=100)] = 20,
    ) -> SatelliteListResponse:
        ...
```

Invalid inputs return a structured `400` automatically. No manual parsing or branching.

---

## Summary

| Concern | Django REST Framework | Litestar |
|---|---|---|
| Routing | Two URL files + `.as_view()` | Single `Controller` class with decorators |
| Serialization | Separate `Serializer` classes, wired manually | Return type annotation = schema = OpenAPI |
| DB session injection | Manual `with get_session()` in every handler | `Provide(provide_db)` generator, injected via `db: Session` type hint |
| 404 handling | `raise NotFound(detail=...)` | `raise NotFoundException(detail=...)` |
| Query param validation | Manual parsing + branching | Annotated type hints, validated automatically |
| OpenAPI / Swagger | Requires `drf-spectacular` (third-party) | Built in, zero config |
| Boilerplate per endpoint | High (URL entry, view class, serializer class) | Low (method on controller + schema) |
| Explicit control flow | High — visible in every handler | Low — framework handles lifecycle |

Both frameworks produce identical JSON responses from the same PostgreSQL data. The difference is in what the framework gives you for free vs. what you wire up yourself.

---

## Architecture

The core insight of this project is that **both frameworks are thin shells over a shared data layer**:

```
core/models.py        ← SQLAlchemy models (schema source of truth)
core/database.py      ← get_session() context manager
core/ingestion.py     ← TLE fetch + upsert logic
core/processing.py    ← sgp4 orbital calculations
```

Neither Django nor Litestar owns the database models. Alembic manages all migrations. Django runs with `DATABASES = {}`, disabling its ORM entirely. This means adding a third framework (FastAPI, Flask, etc.) would only require writing the routing and serialization layer — the data model is already there.

---

## Development

### Run the test suite

```bash
uv run pytest -v
```

### Project structure

```
core/               Shared pipeline logic (no framework dependency)
django_api/         DRF implementation (port 8000)
litestar_api/       Litestar implementation (port 8001)
tests/              Shared test suite covering both frameworks
alembic/            Database migrations
specs/              Requirements, architecture, and implementation plan
```

### Configuration

Copy `.env.example` to `.env`. All defaults work for local development with Docker:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/satellite_db
TLE_API_BASE_URL=https://tle.ivanstanojevic.me
BACKFILL_DAYS=7
DJANGO_HOST=127.0.0.1
DJANGO_PORT=8000
LITESTAR_HOST=127.0.0.1
LITESTAR_PORT=8001
LOG_LEVEL=INFO
```
