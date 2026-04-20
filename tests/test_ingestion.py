"""Tests for core/ingestion.py – fetch and persist TLE data."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from core.ingestion import SATELLITE_TARGETS, fetch_tle, ingest_satellites
from core.models import Satellite, TleRecord
from tests.conftest import ISS_LINE1, ISS_LINE2, NOAA_LINE1, NOAA_LINE2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NORAD_ISS = 25544
_NORAD_NOAA = 33591
_BASE_URL = "https://tle.ivanstanojevic.me"

_EPOCH = "2024-01-01T12:00:00+00:00"


def _tle_payload(name: str, norad_id: int, line1: str, line2: str) -> dict:
    return {"name": name, "satelliteId": norad_id, "date": _EPOCH, "line1": line1, "line2": line2}


# ---------------------------------------------------------------------------
# fetch_tle – unit tests (respx)
# ---------------------------------------------------------------------------


@respx.mock
def test_fetch_tle_success():
    payload = _tle_payload("ISS (ZARYA)", _NORAD_ISS, ISS_LINE1, ISS_LINE2)
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_ISS}").mock(return_value=Response(200, json=payload))

    import httpx

    with httpx.Client(headers={"User-Agent": "test/1.0"}) as client:
        result = fetch_tle(_NORAD_ISS, client, base_url=_BASE_URL)

    assert result["satelliteId"] == _NORAD_ISS
    assert result["line1"] == ISS_LINE1


@respx.mock
def test_fetch_tle_retries_then_raises():
    """Three consecutive 503s should exhaust retries and raise RuntimeError."""
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_ISS}").mock(return_value=Response(503))

    import httpx

    with patch("time.sleep"):  # don't actually wait during tests
        with httpx.Client(headers={"User-Agent": "test/1.0"}) as client:
            with pytest.raises(RuntimeError, match="Failed to fetch"):
                fetch_tle(_NORAD_ISS, client, base_url=_BASE_URL)


# ---------------------------------------------------------------------------
# ingest_satellites – integration tests against real Postgres
# ---------------------------------------------------------------------------


@respx.mock
def test_ingest_happy_path(db_session):
    """Both satellites fetched and inserted on first run."""
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_ISS}").mock(
        return_value=Response(200, json=_tle_payload("ISS (ZARYA)", _NORAD_ISS, ISS_LINE1, ISS_LINE2))
    )
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_NOAA}").mock(
        return_value=Response(200, json=_tle_payload("NOAA 19", _NORAD_NOAA, NOAA_LINE1, NOAA_LINE2))
    )

    summary = ingest_satellites(db_session, base_url=_BASE_URL)
    db_session.commit()

    assert summary == {"fetched": 2, "inserted": 2, "skipped": 0}
    satellites = db_session.execute(select(Satellite)).scalars().all()
    assert len(satellites) == 2
    tle_records = db_session.execute(select(TleRecord)).scalars().all()
    assert len(tle_records) == 2


@respx.mock
def test_ingest_deduplication(db_session):
    """Re-ingesting the same epoch inserts 0 new records."""
    for _ in range(2):
        respx.get(f"{_BASE_URL}/api/tle/{_NORAD_ISS}").mock(
            return_value=Response(200, json=_tle_payload("ISS (ZARYA)", _NORAD_ISS, ISS_LINE1, ISS_LINE2))
        )
        respx.get(f"{_BASE_URL}/api/tle/{_NORAD_NOAA}").mock(
            return_value=Response(200, json=_tle_payload("NOAA 19", _NORAD_NOAA, NOAA_LINE1, NOAA_LINE2))
        )

    # First run
    ingest_satellites(db_session, base_url=_BASE_URL)
    db_session.commit()

    # Second run – same epoch → ON CONFLICT DO NOTHING
    summary = ingest_satellites(db_session, base_url=_BASE_URL)
    db_session.commit()

    assert summary["inserted"] == 0
    assert summary["skipped"] == 2
    # Still only 2 TLE records total
    count = db_session.execute(select(TleRecord)).scalars().all()
    assert len(count) == 2


@respx.mock
def test_ingest_partial_failure(db_session):
    """When one satellite fails all retries, the other is still inserted."""
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_ISS}").mock(return_value=Response(503))
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_NOAA}").mock(
        return_value=Response(200, json=_tle_payload("NOAA 19", _NORAD_NOAA, NOAA_LINE1, NOAA_LINE2))
    )

    with patch("time.sleep"):
        summary = ingest_satellites(db_session, base_url=_BASE_URL)
    db_session.commit()

    assert summary["fetched"] == 1
    assert summary["inserted"] == 1
    records = db_session.execute(select(TleRecord)).scalars().all()
    assert len(records) == 1


@respx.mock
def test_ingest_satellite_name_updated(db_session):
    """An existing satellite whose name changed in the API gets updated in the DB."""
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_ISS}").mock(
        return_value=Response(200, json=_tle_payload("ISS RENAMED", _NORAD_ISS, ISS_LINE1, ISS_LINE2))
    )
    respx.get(f"{_BASE_URL}/api/tle/{_NORAD_NOAA}").mock(
        return_value=Response(200, json=_tle_payload("NOAA 19", _NORAD_NOAA, NOAA_LINE1, NOAA_LINE2))
    )

    ingest_satellites(db_session, base_url=_BASE_URL)
    db_session.commit()

    iss = db_session.execute(
        select(Satellite).where(Satellite.norad_id == _NORAD_ISS)
    ).scalar_one()
    assert iss.name == "ISS RENAMED"
