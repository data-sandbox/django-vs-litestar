"""Flask-smorest MethodView handlers for the satellite TLE API."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from core.database import get_session
from core.queries import (
    build_pagination_urls,
    get_satellite_detail,
    get_satellite_history,
    get_satellite_list,
)
from flask_api.satellites.schemas import (
    SatelliteDetailSchema,
    SatelliteListQuerySchema,
    SatelliteListResponseSchema,
    TleHistoryQuerySchema,
    TleHistoryResponseSchema,
)

blp = Blueprint(
    "satellites",
    __name__,
    url_prefix="/api/v1/satellites",
    description="Satellite TLE read-only endpoints.",
)


@blp.route("/")
class SatelliteList(MethodView):
    """List all satellites with their latest processed orbital parameters."""

    @blp.arguments(SatelliteListQuerySchema, location="query")
    @blp.response(200, SatelliteListResponseSchema)
    def get(self, args: dict) -> dict:
        """Return a paginated satellite list, optionally filtered by orbit type."""
        orbit_type = args["orbit_type"]
        page = args["page"]
        page_size = args["page_size"]

        with get_session() as session:
            count, rows = get_satellite_list(
                session, orbit_type=orbit_type, page=page, page_size=page_size
            )

        next_url, prev_url = build_pagination_urls(
            "/api/v1/satellites/",
            page,
            page_size,
            count,
            extra_params={"orbit_type": orbit_type},
        )
        return {
            "count": count,
            "next": next_url,
            "previous": prev_url,
            "results": list(rows),
        }


@blp.route("/<int:norad_id>")
class SatelliteDetail(MethodView):
    """Retrieve full orbital detail for a single satellite by NORAD ID."""

    @blp.response(200, SatelliteDetailSchema)
    def get(self, norad_id: int) -> object:
        """Return the detail record for the satellite identified by norad_id."""
        with get_session() as session:
            row = get_satellite_detail(session, norad_id)

        if row is None:
            abort(404, message=f"Satellite with NORAD ID {norad_id} not found.")

        return row


@blp.route("/<int:norad_id>/history")
class SatelliteHistory(MethodView):
    """List historical TLE snapshots for a satellite, filterable by date range."""

    @blp.arguments(TleHistoryQuerySchema, location="query")
    @blp.response(200, TleHistoryResponseSchema)
    def get(self, args: dict, norad_id: int) -> dict:
        """Return a paginated list of raw TLE records for the given satellite."""
        page = args["page"]
        page_size = args["page_size"]
        from_date = args["from_date"]
        to_date = args["to_date"]

        with get_session() as session:
            exists, count, rows = get_satellite_history(
                session,
                norad_id,
                from_date=from_date,
                to_date=to_date,
                page=page,
                page_size=page_size,
            )

        if not exists:
            abort(404, message=f"Satellite with NORAD ID {norad_id} not found.")

        next_url, prev_url = build_pagination_urls(
            f"/api/v1/satellites/{norad_id}/history/",
            page,
            page_size,
            count,
            extra_params={"from_date": from_date, "to_date": to_date},
        )
        return {
            "count": count,
            "next": next_url,
            "previous": prev_url,
            "results": list(rows),
        }
