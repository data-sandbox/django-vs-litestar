"""FastAPI application factory for the satellite TLE API."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from fastapi_api.satellites.router import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Satellite TLE API (FastAPI)",
        description=(
            "Read-only REST API for satellite TLE orbital data. "
            "FastAPI implementation — compare with the Django version at :8000, "
            "Litestar at :8001, and Flask at :8003."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Redirect the root path to the Swagger UI docs."""
        return RedirectResponse(url="/docs", status_code=302)

    app.include_router(router)
    return app


app = create_app()
