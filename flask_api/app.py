"""Flask application factory for the satellite TLE API."""

from flask import redirect
from flask_openapi3 import Info, OpenAPI

from flask_api.satellites.views import blp as satellites_blp


def create_app() -> OpenAPI:
    """Create and configure the Flask application."""
    info = Info(title="Satellite TLE API (Flask)", version="v1")
    app = OpenAPI(__name__, info=info)
    app.url_map.strict_slashes = False

    app.register_api(satellites_blp)

    @app.get("/")
    def root() -> object:
        """Redirect the root path to the Swagger UI docs."""
        return redirect("/openapi/swagger")

    return app


app = create_app()
