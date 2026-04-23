# Which API? A Django, Litestar, FastAPI, Flask Comparison

The project creates a satellite TLE pipeline implemented four times — with **Django**, **Litestar**, **FastAPI**, and **Flask** — sharing a single SQLAlchemy data layer. It fetches live Two-Line Element (TLE) orbital data for the ISS and NOAA 19, processes it with `sgp4` to compute apogee, perigee, period, and orbit type, then serves the results through identical REST API endpoints in all four frameworks. The goal is a concrete, side-by-side comparison of how each framework handles routing, serialization, dependency injection, and error handling.

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

### 3 — Run all four APIs

In four separate terminals:

```bash
uv run python main.py run-django      # http://localhost:8000
uv run python main.py run-litestar    # http://localhost:8001
uv run python main.py run-fastapi     # http://localhost:8002
uv run python main.py run-flask       # http://localhost:8003
```

All servers read from the same PostgreSQL tables. The same request to any port returns the same JSON:

```bash
curl http://localhost:8000/api/v1/satellites/        # Django
curl http://localhost:8001/api/v1/satellites/        # Litestar
curl http://localhost:8002/api/v1/satellites/        # FastAPI
curl http://localhost:8003/api/v1/satellites/        # Flask
```

Interactive OpenAPI docs are at `/docs` on every server.


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
    ├──▶  litestar_api/ (port 8001)   Litestar Controller + Pydantic schemas
    ├──▶  fastapi_api/  (port 8002)   FastAPI APIRouter + Pydantic schemas
    └──▶  flask_api/    (port 8003)   flask-smorest Blueprint + marshmallow schemas
```

All four framework layers are read-only. All writes happen through `core/`.

---

## API Endpoints

All three endpoints are available on all four ports with identical request/response shapes.

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

All four implementations live in the same repository and share a single data layer (`core/`). The differences below are purely about what each framework requires to expose the same endpoint.

---

### 1. Routing

**Django** — URLs are registered in two separate files. Each class must be explicitly wired with `.as_view()`:

```python
# django_api/config/urls.py
urlpatterns = [path("api/v1/", include("django_api.satellites.urls"))]

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

**FastAPI** — An `APIRouter` with `prefix`. The router is mounted onto the app; more-specific paths must be registered first to avoid ambiguous matching:

```python
router = APIRouter(prefix="/api/v1/satellites", tags=["satellites"])

@router.get("/")
def list_satellites(...) -> SatelliteListResponse: ...

@router.get("/{norad_id}/history")   # registered before /{norad_id}
def get_satellite_history(norad_id: int, ...) -> TleHistoryResponse: ...

@router.get("/{norad_id}")
def get_satellite(norad_id: int, ...) -> SatelliteDetail: ...

# fastapi_api/app.py
app.include_router(router)
```

**Flask (flask-smorest)** — A `Blueprint` with `url_prefix`. `MethodView` classes bind HTTP verbs to methods:

```python
blp = Blueprint("satellites", __name__, url_prefix="/api/v1/satellites")

@blp.route("/")
class SatelliteList(MethodView):
    def get(self, query_args): ...

@blp.route("/<int:norad_id>/history")
class SatelliteHistory(MethodView):
    def get(self, query_args, norad_id): ...

@blp.route("/<int:norad_id>")
class SatelliteDetail(MethodView):
    def get(self, norad_id): ...

# flask_api/app.py
api.register_blueprint(blp)
```

---

### 2. Serialization / Response Schemas

**Django** — Serializer classes are defined separately from views. The type contract between view and serializer is implicit:

```python
# django_api/satellites/serializers.py
class SatelliteListSerializer(Serializer):
    norad_id        = IntegerField()
    name            = CharField()
    orbit_type      = CharField()
    period_minutes  = FloatField()
    apogee_km       = FloatField()
    perigee_km      = FloatField()
    inclination_deg = FloatField()
    last_updated    = DateTimeField()

# django_api/satellites/views.py
class SatelliteListView(APIView):
    def get(self, request):
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

**FastAPI** — Same Pydantic `BaseModel` pattern as Litestar. The schema is declared via return-type annotation or explicitly on the `response_model` parameter:

```python
# fastapi_api/satellites/schemas.py — identical structure to litestar_api/
class SatelliteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    norad_id: int
    ...

# fastapi_api/satellites/router.py
@router.get("/", response_model=SatelliteListResponse)
def list_satellites(...):
    ...
```

`ConfigDict(from_attributes=True)` allows both Litestar and FastAPI to serialize SQLAlchemy Row objects directly.

**Flask (flask-smorest)** — Uses marshmallow `Schema` classes wired to routes via `@blp.arguments` (deserialize request) and `@blp.response` (serialize response):

```python
# flask_api/satellites/schemas.py
class SatelliteListItemSchema(ma.Schema):
    norad_id        = ma.fields.Int(dump_default=None)
    name            = ma.fields.Str(dump_default=None)
    orbit_type      = ma.fields.Str(dump_default=None)
    period_minutes  = ma.fields.Float(dump_default=None)
    apogee_km       = ma.fields.Float(dump_default=None)
    perigee_km      = ma.fields.Float(dump_default=None)
    inclination_deg = ma.fields.Float(dump_default=None)
    last_updated    = ma.fields.DateTime(dump_default=None)

# flask_api/satellites/views.py
@blp.route("/")
class SatelliteList(MethodView):
    @blp.arguments(SatelliteListQuerySchema, location="query")
    @blp.response(200, SatelliteListResponseSchema)
    def get(self, query_args):
        ...
```

The `@blp.response` decorator runs marshmallow serialization and registers the schema in the OpenAPI spec automatically.

---

### 3. Dependency Injection (Database Session)

**Django** — No built-in DI system. Sessions are acquired manually inside each handler:

```python
class SatelliteListView(APIView):
    def get(self, request):
        with get_session() as session:   # repeated in every handler
            rows = session.execute(...).all()
        return Response(SatelliteListSerializer(rows, many=True).data)
```

**Litestar** — A `provide_db` generator is registered at app startup via `Provide`. Litestar resolves `db: Session` from the dependency graph:

```python
# litestar_api/app.py
def provide_db() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session

app = Litestar(
    route_handlers=[SatelliteController],
    dependencies={"db": Provide(provide_db)},
)

# litestar_api/satellites/controllers.py
    @get("", sync_to_thread=False)
    def list_satellites(self, db: Session, ...) -> SatelliteListResponse:
        rows = db.execute(...).all()   # db injected automatically
```

**FastAPI** — Uses `Depends()`. The dependency is a generator that yields a session; FastAPI manages teardown automatically:

```python
# fastapi_api/satellites/router.py
def get_db() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session

@router.get("/", response_model=SatelliteListResponse)
def list_satellites(
    db: Annotated[Session, Depends(get_db)],
    ...
):
    rows = db.execute(...).all()
```

**Flask** — No DI system. Like Django, sessions are acquired manually. The module-level `get_session` reference is patchable for testing:

```python
@blp.route("/")
class SatelliteList(MethodView):
    @blp.arguments(SatelliteListQuerySchema, location="query")
    @blp.response(200, SatelliteListResponseSchema)
    def get(self, query_args):
        with get_session() as session:   # repeated in every handler
            rows = session.execute(...).all()
        return {"count": count, "results": list(rows), ...}
```

---

### 4. 404 Error Handling

**Django** — Raise DRF's `NotFound`; DRF's exception handler serializes it:

```python
from rest_framework.exceptions import NotFound
raise NotFound(detail=f"Satellite with NORAD ID {norad_id} not found.")
```

**Litestar** — Raise `NotFoundException`; identical wire format:

```python
from litestar.exceptions import NotFoundException
raise NotFoundException(detail=f"Satellite with NORAD ID {norad_id} not found.")
```

**FastAPI** — Raise `HTTPException`:

```python
from fastapi import HTTPException
raise HTTPException(status_code=404, detail=f"Satellite with NORAD ID {norad_id} not found.")
```

**Flask** — Call `abort()`:

```python
from flask import abort
abort(404, message=f"Satellite with NORAD ID {norad_id} not found.")
```

All four return `{"detail": "..."}` with a `404` status — the same wire format despite different APIs.

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
        ...
```

**Litestar** — Parameters are declared in the function signature. Litestar validates them automatically and returns `400` on error:

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

**FastAPI** — Same approach as Litestar; FastAPI uses Pydantic and returns `422` on error:

```python
_OrbitType = Literal["LEO", "MEO", "GEO", "HEO", "OTHER"]

@router.get("/", response_model=SatelliteListResponse)
def list_satellites(
    db: Annotated[Session, Depends(get_db)],
    orbit_type: _OrbitType | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    ...
```

**Flask (flask-smorest)** — A marshmallow `Schema` is used as the query-argument schema. flask-smorest validates it before calling the handler and returns `422` on error:

```python
class SatelliteListQuerySchema(ma.Schema):
    orbit_type = ma.fields.Str(load_default=None, allow_none=True)
    page       = ma.fields.Int(load_default=1, validate=ma.validate.Range(min=1))
    page_size  = ma.fields.Int(load_default=20, validate=ma.validate.Range(min=1, max=100))

    @ma.validates("orbit_type")
    def validate_orbit_type(self, value: str | None, **kwargs: object) -> None:
        if value is not None and value not in {"LEO", "MEO", "GEO", "HEO", "OTHER"}:
            raise ma.ValidationError("Must be one of: LEO, MEO, GEO, HEO, OTHER.")

@blp.route("/")
class SatelliteList(MethodView):
    @blp.arguments(SatelliteListQuerySchema, location="query")
    def get(self, query_args):   # validated dict injected automatically
        ...
```

---

## Summary

| Concern | Django (DRF) | Litestar | FastAPI | Flask (flask-smorest) |
|---|---|---|---|---|
| Routing | Two URL files + `.as_view()` | `Controller` class with decorators | `APIRouter` + `include_router()` | `Blueprint` + `MethodView` |
| Serialization | `Serializer` classes, wired manually | Return type = schema (Pydantic) | `response_model` on decorator (Pydantic) | `@blp.response` + marshmallow `Schema` |
| DB session injection | Manual `with get_session()` per handler | `Provide(provide_db)` generator, injected via type hint | `Depends(get_db)` generator | Manual `with get_session()` per handler |
| 404 handling | `raise NotFound(detail=...)` | `raise NotFoundException(detail=...)` | `raise HTTPException(status_code=404)` | `abort(404, message=...)` |
| Query param validation | Manual parsing + branching | Annotated type hints, `400` on error | Annotated type hints, `422` on error | marshmallow `Schema` + `@blp.arguments`, `422` on error |
| OpenAPI / Swagger | Requires `drf-spectacular` (third-party) | Built in, zero config | Built in, zero config | flask-smorest (extension, minimal config) |
| Boilerplate per endpoint | High | Low | Low | Medium |
| Validation error status | `400` | `400` | `422` | `422` |

All four frameworks produce identical JSON responses from the same PostgreSQL data. The differences are in what each framework provides for free versus what you wire up yourself.

---

## Architecture

The core insight of this project is that **all four frameworks are thin shells over a shared data layer**:

```
core/models.py        ← SQLAlchemy models (schema source of truth)
core/database.py      ← get_session() context manager
core/ingestion.py     ← TLE fetch + upsert logic
core/processing.py    ← sgp4 orbital calculations
```

No framework owns the database models. Alembic manages all migrations. Django runs with `DATABASES = {}`, disabling its ORM entirely. Adding a new framework only requires writing the routing and serialization layer — the data model is already there.

---

## Development

### Run the test suite

```bash
uv run pytest -v
```

56 tests cover all four implementations using real PostgreSQL via [testcontainers](https://testcontainers-python.readthedocs.io/).

### Project structure

```
core/               Shared pipeline logic (no framework dependency)
django_api/         DRF implementation (port 8000)
litestar_api/       Litestar implementation (port 8001)
fastapi_api/        FastAPI implementation (port 8002)
flask_api/          Flask (flask-smorest) implementation (port 8003)
tests/              Shared test suite covering all four frameworks
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
