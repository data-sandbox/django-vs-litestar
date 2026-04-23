from collections.abc import AsyncGenerator

from litestar import Litestar, get
from litestar.di import Provide
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.response import Redirect
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_async_session
from litestar_api.satellites.controllers import SatelliteController


async def provide_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider: yields an AsyncSession for the duration of the request."""
    async with get_async_session() as session:
        yield session


@get("/", include_in_schema=False)
async def root_redirect() -> Redirect:
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
