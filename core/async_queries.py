"""Async SQLAlchemy query helpers for the FastAPI and Litestar API layers.

These are async equivalents of the functions in ``core/queries.py``. The query
construction (``select`` / ``join`` / ``where``) is identical — SQLAlchemy's Core
expression language is driver-agnostic. Only the *execution* calls change: each
``session.execute(...)`` becomes ``await session.execute(...)``.

Django and Flask continue to use the sync versions in ``core/queries.py``.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ProcessedTle, Satellite, TleRecord
from core.queries import _latest_processed_subq


async def get_satellite_list(
    session: AsyncSession,
    orbit_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list]:
    """Return (total_count, rows) for the satellite list endpoint."""
    max_ep = _latest_processed_subq()

    base = (
        select(
            Satellite.norad_id,
            Satellite.name,
            ProcessedTle.orbit_type,
            ProcessedTle.period_minutes,
            ProcessedTle.apogee_km,
            ProcessedTle.perigee_km,
            ProcessedTle.inclination_deg,
            TleRecord.epoch.label("last_updated"),
        )
        .join(max_ep, max_ep.c.satellite_id == Satellite.id)
        .join(
            TleRecord,
            (TleRecord.satellite_id == Satellite.id) & (TleRecord.epoch == max_ep.c.max_epoch),
        )
        .join(ProcessedTle, ProcessedTle.tle_record_id == TleRecord.id)
        .order_by(Satellite.norad_id)
    )

    if orbit_type:
        base = base.where(ProcessedTle.orbit_type == orbit_type)

    count = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.offset((page - 1) * page_size).limit(page_size))).all()
    return count, rows


async def get_satellite_detail(session: AsyncSession, norad_id: int):
    """Return a single row with full orbital detail, or None if not found / not processed."""
    max_ep = _latest_processed_subq()

    stmt = (
        select(
            Satellite.norad_id,
            Satellite.name,
            ProcessedTle.orbit_type,
            ProcessedTle.period_minutes,
            ProcessedTle.apogee_km,
            ProcessedTle.perigee_km,
            ProcessedTle.inclination_deg,
            ProcessedTle.eccentricity,
            ProcessedTle.mean_motion_rev_per_day,
            TleRecord.epoch.label("last_updated"),
        )
        .join(max_ep, max_ep.c.satellite_id == Satellite.id)
        .join(
            TleRecord,
            (TleRecord.satellite_id == Satellite.id) & (TleRecord.epoch == max_ep.c.max_epoch),
        )
        .join(ProcessedTle, ProcessedTle.tle_record_id == TleRecord.id)
        .where(Satellite.norad_id == norad_id)
    )
    return (await session.execute(stmt)).one_or_none()


async def get_satellite_history(
    session: AsyncSession,
    norad_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[bool, int, list]:
    """Return (satellite_exists, total_count, rows) for the history endpoint."""
    satellite = (
        await session.execute(select(Satellite).where(Satellite.norad_id == norad_id))
    ).scalar_one_or_none()

    if satellite is None:
        return False, 0, []

    base = (
        select(
            TleRecord.tle_line1,
            TleRecord.tle_line2,
            TleRecord.epoch,
            TleRecord.fetched_at,
        )
        .where(TleRecord.satellite_id == satellite.id)
        .order_by(TleRecord.epoch.desc())
    )

    if from_date:
        base = base.where(
            TleRecord.epoch >= datetime.combine(from_date, time.min).replace(tzinfo=UTC)
        )
    if to_date:
        base = base.where(
            TleRecord.epoch
            < datetime.combine(to_date + timedelta(days=1), time.min).replace(tzinfo=UTC)
        )

    count = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.offset((page - 1) * page_size).limit(page_size))).all()
    return True, count, rows
