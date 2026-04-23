"""Flask application factory for the satellite TLE API."""

from flask import Flask, redirect
from flask_smorest import Api

from flask_api.satellites.views import blp as satellites_blp


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.update(
        {
            "API_TITLE": "Satellite TLE API (Flask)",
            "API_VERSION": "v1",
            "OPENAPI_VERSION": "3.0.3",
            "OPENAPI_URL_PREFIX": "/",
            "OPENAPI_SWAGGER_UI_PATH": "/docs",
            "OPENAPI_SWAGGER_UI_URL": "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
        }
    )

    api = Api(app)
    api.register_blueprint(satellites_blp)

    @app.get("/")
    def root() -> object:
        """Redirect the root path to the Swagger UI docs."""
        return redirect("/docs")

    return app


app = create_app()
