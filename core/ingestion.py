import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.models import Satellite, TleRecord

logger = logging.getLogger(__name__)

SATELLITE_TARGETS: list[tuple[str, int]] = [
    ("ISS (ZARYA)", 25544),
    ("NOAA 19", 33591),
]

_RETRY_DELAYS = (1, 2, 4)


def fetch_tle(
    norad_id: int, client: httpx.Client, base_url: str = "https://tle.ivanstanojevic.me"
) -> dict:
    """Fetch a single TLE record by NORAD ID with up to 3 retries and exponential backoff."""
    url = f"{base_url}/api/tle/{norad_id}"
    last_exc: Exception | None = None
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            response = client.get(url, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "TLE API error",
                extra={"status_code": exc.response.status_code, "url": url, "attempt": attempt},
            )
            last_exc = exc
        except httpx.RequestError as exc:
            logger.warning(
                "TLE API request error", extra={"url": url, "attempt": attempt, "error": str(exc)}
            )
            last_exc = exc

        if delay is not None:
            time.sleep(delay)

    raise RuntimeError(
        f"Failed to fetch NORAD {norad_id} after {len(_RETRY_DELAYS) + 1} attempts"
    ) from last_exc


def _parse_epoch(epoch_str: str) -> datetime:
    """Parse the ISO-8601 epoch string returned by the TLE API into a UTC datetime."""
    # The API returns strings like "2026-04-18T12:00:00+00:00" or "2026-04-18T12:00:00Z"
    dt = datetime.fromisoformat(epoch_str.replace("Z", "+00:00"))
    return dt.astimezone(UTC)


def ingest_satellites(
    session: Session,
    fetched_at: datetime | None = None,
    epoch_offset: timedelta | None = None,
    base_url: str = "https://tle.ivanstanojevic.me",
) -> dict:
    """Fetch TLE data for both target satellites and persist to the database.

    ``epoch_offset``: when provided, subtract this delta from the TLE epoch before
    storing.  Used by the ``backfill`` command to produce distinct (satellite_id,
    epoch) pairs from an API that only returns the current TLE — the API has no
    history endpoint, so backfill history is synthetic.

    Returns a summary dict: {"fetched": n, "inserted": n, "skipped": n}.
    """
    if fetched_at is None:
        fetched_at = datetime.now(UTC)

    total_fetched = 0
    total_inserted = 0
    total_skipped = 0

    with httpx.Client(headers={"User-Agent": "satellite-pipeline/1.0"}) as client:
        for name, norad_id in SATELLITE_TARGETS:
            try:
                data = fetch_tle(norad_id, client, base_url=base_url)
            except RuntimeError:
                logger.error(
                    "Skipping satellite after failed fetch",
                    extra={"norad_id": norad_id, "satellite_name": name},
                )
                continue

            total_fetched += 1

            # Upsert satellite row
            stmt = (
                pg_insert(Satellite)
                .values(norad_id=norad_id, name=data.get("name", name))
                .on_conflict_do_update(
                    index_elements=["norad_id"],
                    set_={"name": data.get("name", name), "updated_at": datetime.now(UTC)},
                )
                .returning(Satellite.id)
            )
            result = session.execute(stmt)
            satellite_id: int = result.scalar_one()

            # Parse epoch; shift it for synthetic backfill days so that each
            # backfill iteration produces a unique (satellite_id, epoch) pair.
            # The API only returns the current TLE, so without this shift all
            # backfill days would collide on the same epoch and be skipped.
            epoch = _parse_epoch(data["date"])
            if epoch_offset:
                epoch = epoch - epoch_offset

            # Insert TLE record, skip on duplicate (satellite_id, epoch)
            tle_stmt = (
                pg_insert(TleRecord)
                .values(
                    satellite_id=satellite_id,
                    tle_line1=data["line1"],
                    tle_line2=data["line2"],
                    epoch=epoch,
                    fetched_at=fetched_at,
                )
                .on_conflict_do_nothing(constraint="uq_tle_records_satellite_epoch")
                .returning(TleRecord.id)
            )
            tle_result = session.execute(tle_stmt)
            inserted_id = tle_result.scalar_one_or_none()
            if inserted_id is not None:
                total_inserted += 1
            else:
                total_skipped += 1

    summary = {"fetched": total_fetched, "inserted": total_inserted, "skipped": total_skipped}
    logger.info("Ingestion complete", extra=summary)
    return summary
