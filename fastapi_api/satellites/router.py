"""FastAPI router for satellite TLE read-only endpoints."""

from collections.abc import Generator
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.database import get_session
from core.queries import (
    build_pagination_urls,
    get_satellite_detail,
    get_satellite_history,
    get_satellite_list,
)
from fastapi_api.satellites.schemas import (
    SatelliteDetail,
    SatelliteListItem,
    SatelliteListResponse,
    TleHistoryItem,
    TleHistoryResponse,
)

router = APIRouter(prefix="/api/v1/satellites", tags=["satellites"])

_OrbitType = Literal["LEO", "MEO", "GEO", "HEO", "OTHER"]


def get_db() -> Generator[Session, None, None]:
    """Dependency provider: yields a SQLAlchemy session for the duration of the request."""
    with get_session() as session:
        yield session


@router.get("/{norad_id}/history", response_model=TleHistoryResponse)
def get_history(
    norad_id: int,
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    from_date: date | None = None,
    to_date: date | None = None,
) -> TleHistoryResponse:
    """Return paginated TLE history for a satellite, filterable by date range."""
    exists, count, rows = get_satellite_history(
        db,
        norad_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite with NORAD ID {norad_id} not found.",
        )
    next_url, prev_url = build_pagination_urls(
        f"/api/v1/satellites/{norad_id}/history/",
        page,
        page_size,
        count,
        extra_params={"from_date": from_date, "to_date": to_date},
    )
    return TleHistoryResponse(
        count=count,
        next=next_url,
        previous=prev_url,
        results=[TleHistoryItem.model_validate(row) for row in rows],
    )


@router.get("/{norad_id}", response_model=SatelliteDetail)
def get_satellite(
    norad_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> SatelliteDetail:
    """Return full orbital detail for the satellite identified by norad_id."""
    row = get_satellite_detail(db, norad_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Satellite with NORAD ID {norad_id} not found.",
        )
    return SatelliteDetail.model_validate(row)


@router.get("/", response_model=SatelliteListResponse)
def list_satellites(
    db: Annotated[Session, Depends(get_db)],
    orbit_type: _OrbitType | None = Query(None),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SatelliteListResponse:
    """Return a paginated satellite list, optionally filtered by orbit type."""
    count, rows = get_satellite_list(db, orbit_type=orbit_type, page=page, page_size=page_size)
    next_url, prev_url = build_pagination_urls(
        "/api/v1/satellites/",
        page,
        page_size,
        count,
        extra_params={"orbit_type": orbit_type},
    )
    return SatelliteListResponse(
        count=count,
        next=next_url,
        previous=prev_url,
        results=[SatelliteListItem.model_validate(row) for row in rows],
    )
