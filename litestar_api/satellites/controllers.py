from datetime import date
from typing import Annotated, Literal

from litestar import Controller, get
from litestar.exceptions import NotFoundException
from litestar.params import Parameter
from sqlalchemy.ext.asyncio import AsyncSession

from core.async_queries import (
    get_satellite_detail,
    get_satellite_history,
    get_satellite_list,
)
from core.queries import build_pagination_urls
from litestar_api.satellites.schemas import (
    SatelliteDetail,
    SatelliteListItem,
    SatelliteListResponse,
    TleHistoryItem,
    TleHistoryResponse,
)

_ORBIT_TYPES = Literal["LEO", "MEO", "GEO", "HEO", "OTHER"]


class SatelliteController(Controller):
    """Litestar controller for satellite TLE read-only endpoints."""

    path = "/api/v1/satellites"

    @get("")
    async def list_satellites(
        self,
        db: AsyncSession,
        orbit_type: _ORBIT_TYPES | None = None,
        page: Annotated[int, Parameter(ge=1)] = 1,
        page_size: Annotated[int, Parameter(ge=1, le=100)] = 20,
    ) -> SatelliteListResponse:
        """Return a paginated satellite list, optionally filtered by orbit type."""
        count, rows = await get_satellite_list(
            db, orbit_type=orbit_type, page=page, page_size=page_size
        )
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

    @get("/{norad_id:int}")
    async def get_satellite(self, db: AsyncSession, norad_id: int) -> SatelliteDetail:
        """Return full orbital detail for the satellite identified by norad_id."""
        row = await get_satellite_detail(db, norad_id)
        if row is None:
            raise NotFoundException(detail=f"Satellite with NORAD ID {norad_id} not found.")
        return SatelliteDetail.model_validate(row)

    @get("/{norad_id:int}/history")
    async def get_history(
        self,
        db: AsyncSession,
        norad_id: int,
        page: Annotated[int, Parameter(ge=1)] = 1,
        page_size: Annotated[int, Parameter(ge=1, le=100)] = 20,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> TleHistoryResponse:
        """Return paginated TLE history for a satellite, filterable by date range."""
        exists, count, rows = await get_satellite_history(
            db,
            norad_id,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )
        if not exists:
            raise NotFoundException(detail=f"Satellite with NORAD ID {norad_id} not found.")

        next_url, prev_url = build_pagination_urls(
            f"/api/v1/satellites/{norad_id}/history",
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
