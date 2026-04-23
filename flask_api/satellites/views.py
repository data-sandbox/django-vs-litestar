"""Flask-openapi3 route handlers for the satellite TLE API."""

from flask import abort
from flask_openapi3 import APIBlueprint
from pydantic import BaseModel

from core.database import get_session
from core.queries import (
    build_pagination_urls,
    get_satellite_detail,
    get_satellite_history,
    get_satellite_list,
)
from flask_api.satellites.schemas import (
    SatelliteDetail,
    SatelliteListItem,
    SatelliteListQuery,
    SatelliteListResponse,
    TleHistoryItem,
    TleHistoryQuery,
    TleHistoryResponse,
)

blp = APIBlueprint("satellites", __name__, url_prefix="/api/v1/satellites")


class _SatelliteDetailPath(BaseModel):
    norad_id: int


class _TleHistoryPath(BaseModel):
    norad_id: int


@blp.get("/", responses={200: SatelliteListResponse})
def list_satellites(query: SatelliteListQuery) -> dict:
    """Return a paginated satellite list, optionally filtered by orbit type."""
    with get_session() as session:
        count, rows = get_satellite_list(
            session, orbit_type=query.orbit_type, page=query.page, page_size=query.page_size
        )

    next_url, prev_url = build_pagination_urls(
        "/api/v1/satellites/",
        query.page,
        query.page_size,
        count,
        extra_params={"orbit_type": query.orbit_type},
    )
    return SatelliteListResponse(
        count=count,
        next=next_url,
        previous=prev_url,
        results=[SatelliteListItem.model_validate(row) for row in rows],
    ).model_dump(mode="json")


@blp.get("/<int:norad_id>", responses={200: SatelliteDetail})
def get_satellite(path: _SatelliteDetailPath) -> dict:
    """Return full orbital detail for the satellite identified by norad_id."""
    with get_session() as session:
        row = get_satellite_detail(session, path.norad_id)

    if row is None:
        abort(404)

    return SatelliteDetail.model_validate(row).model_dump(mode="json")


@blp.get("/<int:norad_id>/history", responses={200: TleHistoryResponse})
def get_history(path: _TleHistoryPath, query: TleHistoryQuery) -> dict:
    """Return a paginated list of raw TLE records for the given satellite."""
    with get_session() as session:
        exists, count, rows = get_satellite_history(
            session,
            path.norad_id,
            from_date=query.from_date,
            to_date=query.to_date,
            page=query.page,
            page_size=query.page_size,
        )

    if not exists:
        abort(404)

    next_url, prev_url = build_pagination_urls(
        f"/api/v1/satellites/{path.norad_id}/history/",
        query.page,
        query.page_size,
        count,
        extra_params={"from_date": query.from_date, "to_date": query.to_date},
    )
    return TleHistoryResponse(
        count=count,
        next=next_url,
        previous=prev_url,
        results=[TleHistoryItem.model_validate(row) for row in rows],
    ).model_dump(mode="json")
