"""Shared SQLAlchemy query helpers used by both the Django and Litestar API layers."""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import ProcessedTle, Satellite, TleRecord


def _latest_processed_subq():
    """Subquery: satellite_id → max(epoch) for satellites that have at least one ProcessedTle."""
    return (
        select(
            TleRecord.satellite_id,
            func.max(TleRecord.epoch).label("max_epoch"),
        )
        .join(ProcessedTle, ProcessedTle.tle_record_id == TleRecord.id)
        .group_by(TleRecord.satellite_id)
        .subquery()
    )


def get_satellite_list(
    session: Session,
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
            (TleRecord.satellite_id == Satellite.id)
            & (TleRecord.epoch == max_ep.c.max_epoch),
        )
        .join(ProcessedTle, ProcessedTle.tle_record_id == TleRecord.id)
        .order_by(Satellite.norad_id)
    )

    if orbit_type:
        base = base.where(ProcessedTle.orbit_type == orbit_type)

    count = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(base.offset((page - 1) * page_size).limit(page_size)).all()
    return count, rows


def get_satellite_detail(session: Session, norad_id: int):
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
            (TleRecord.satellite_id == Satellite.id)
            & (TleRecord.epoch == max_ep.c.max_epoch),
        )
        .join(ProcessedTle, ProcessedTle.tle_record_id == TleRecord.id)
        .where(Satellite.norad_id == norad_id)
    )
    return session.execute(stmt).one_or_none()


def get_satellite_history(
    session: Session,
    norad_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[bool, int, list]:
    """Return (satellite_exists, total_count, rows) for the history endpoint."""
    satellite = session.execute(
        select(Satellite).where(Satellite.norad_id == norad_id)
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
            TleRecord.epoch >= datetime.combine(from_date, time.min).replace(tzinfo=timezone.utc)
        )
    if to_date:
        # Inclusive: up to end of to_date
        base = base.where(
            TleRecord.epoch
            < datetime.combine(to_date + timedelta(days=1), time.min).replace(tzinfo=timezone.utc)
        )

    count = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(base.offset((page - 1) * page_size).limit(page_size)).all()
    return True, count, rows


def build_pagination_urls(
    path: str,
    page: int,
    page_size: int,
    count: int,
    extra_params: dict | None = None,
) -> tuple[str | None, str | None]:
    """Return (next_url, prev_url) as relative paths, or None when at boundary."""
    total_pages = max(1, (count + page_size - 1) // page_size)

    def _build(p: int) -> str:
        params: dict = {"page": p, "page_size": page_size}
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{path}?{qs}"

    next_url = _build(page + 1) if page < total_pages else None
    prev_url = _build(page - 1) if page > 1 else None
    return next_url, prev_url
