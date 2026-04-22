from collections.abc import Generator

from litestar import Litestar, get
from litestar.di import Provide
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.response import Redirect
from sqlalchemy.orm import Session

from core.database import get_session
from litestar_api.satellites.controllers import SatelliteController


def provide_db() -> Generator[Session, None, None]:
    """Dependency provider: yields a SQLAlchemy session for the duration of the request."""
    with get_session() as session:
        yield session


@get("/", include_in_schema=False, sync_to_thread=False)
def root_redirect() -> Redirect:
    """Redirect the root path to the Swagger UI docs."""
    return Redirect(path="/docs")


def create_app() -> Litestar:
    """Instantiate and return the configured Litestar application."""
    return Litestar(
        route_handlers=[SatelliteController, root_redirect],
        dependencies={"db": Provide(provide_db)},
        openapi_config=OpenAPIConfig(
            title="Satellite TLE API (Litestar)",
            description=(
                "Read-only REST API for satellite TLE orbital data. "
                "Litestar implementation — compare with the Django version at :8000."
            ),
            version="1.0.0",
            path="/docs",
            render_plugins=[SwaggerRenderPlugin()],
        ),
    )


app = create_app()
