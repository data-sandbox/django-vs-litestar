from collections.abc import Generator

from litestar import Litestar
from litestar.di import Provide
from litestar.openapi import OpenAPIConfig
from sqlalchemy.orm import Session

from core.database import get_session
from litestar_api.satellites.controllers import SatelliteController


def provide_db() -> Generator[Session, None, None]:
    """Dependency provider: yields a SQLAlchemy session for the duration of the request."""
    with get_session() as session:
        yield session


def create_app() -> Litestar:
    return Litestar(
        route_handlers=[SatelliteController],
        dependencies={"db": Provide(provide_db)},
        openapi_config=OpenAPIConfig(
            title="Satellite TLE API (Litestar)",
            description=(
                "Read-only REST API for satellite TLE orbital data. "
                "Litestar implementation — compare with the Django version at :8000."
            ),
            version="1.0.0",
        ),
    )


app = create_app()
