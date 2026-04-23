"""Tests for the FastAPI satellite API.

Uses FastAPI's dependency_overrides mechanism to inject an ``AsyncSession``
connected to the test database instead of the live development database.

FastAPI returns HTTP 422 (Unprocessable Entity) for query parameter
validation errors, following the JSON Schema / OpenAPI convention.
"""

import pytest
from fastapi.testclient import TestClient

from fastapi_api.satellites.router import get_db


@pytest.fixture()
def fastapi_client(db_session, async_test_engine):
    """Build a FastAPI TestClient with get_db overridden to an AsyncSession on the test DB."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from fastapi_api.app import create_app

    async def override_get_db():
        async with AsyncSession(async_test_engine) as session:
            async with session.begin():
                yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


# ---------------------------------------------------------------------------
# GET /api/v1/satellites/ – list
# ---------------------------------------------------------------------------


def test_list_satellites_empty(fastapi_client):
    """Empty database → 200, count=0, results=[]."""
    resp = fastapi_client.get("/api/v1/satellites/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["results"] == []


def test_list_satellites_returns_processed_records(
    fastapi_client, db_session, processed_tle_factory
):
    """One processed satellite → appears in results."""
    processed_tle_factory()
    db_session.commit()

    resp = fastapi_client.get("/api/v1/satellites/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    item = data["results"][0]
    assert "norad_id" in item
    assert item["orbit_type"] == "LEO"


def test_list_satellites_filter_orbit_type(
    fastapi_client, db_session, processed_tle_factory, satellite_factory, tle_record_factory
):
    """orbit_type filter returns only matching satellites."""
    processed_tle_factory()  # LEO

    sat2 = satellite_factory(norad_id=20000, name="GPS-SVN-1")
    tle2 = tle_record_factory(satellite=sat2, satellite_id=sat2.id)
    processed_tle_factory(
        tle_record=tle2,
        tle_record_id=tle2.id,
        orbit_type="MEO",
        perigee_km=20_000.0,
        apogee_km=20_200.0,
    )
    db_session.commit()

    resp = fastapi_client.get("/api/v1/satellites/?orbit_type=MEO")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["orbit_type"] == "MEO"


def test_list_satellites_invalid_orbit_type(fastapi_client):
    """Invalid orbit_type value → 422 (FastAPI/Pydantic validation error)."""
    resp = fastapi_client.get("/api/v1/satellites/?orbit_type=INVALID")
    assert resp.status_code == 422


def test_list_satellites_pagination(
    fastapi_client, db_session, satellite_factory, tle_record_factory, processed_tle_factory
):
    """page_size=1 with two satellites returns next link and one result."""
    processed_tle_factory()
    sat2 = satellite_factory(norad_id=20001, name="SAT-2")
    tle2 = tle_record_factory(satellite=sat2, satellite_id=sat2.id)
    processed_tle_factory(tle_record=tle2, tle_record_id=tle2.id)
    db_session.commit()

    resp = fastapi_client.get("/api/v1/satellites/?page_size=1&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["results"]) == 1
    assert data["next"] is not None


# ---------------------------------------------------------------------------
# GET /api/v1/satellites/{norad_id} – detail
# ---------------------------------------------------------------------------


def test_satellite_detail_found(fastapi_client, db_session, processed_tle_factory):
    """Existing satellite → 200 with full orbital fields."""
    ptl = processed_tle_factory()
    db_session.commit()
    norad_id = ptl.tle_record.satellite.norad_id

    resp = fastapi_client.get(f"/api/v1/satellites/{norad_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["norad_id"] == norad_id
    assert "eccentricity" in data
    assert "mean_motion_rev_per_day" in data


def test_satellite_detail_not_found(fastapi_client):
    """Unknown NORAD ID → 404."""
    resp = fastapi_client.get("/api/v1/satellites/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/satellites/{norad_id}/history – history
# ---------------------------------------------------------------------------


def test_satellite_history_found(fastapi_client, db_session, tle_record_factory):
    """Satellite with TLE records → history returns them."""
    tle = tle_record_factory()
    db_session.commit()
    norad_id = tle.satellite.norad_id

    resp = fastapi_client.get(f"/api/v1/satellites/{norad_id}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["tle_line1"] == tle.tle_line1


def test_satellite_history_not_found(fastapi_client):
    """Unknown NORAD ID → 404."""
    resp = fastapi_client.get("/api/v1/satellites/99999/history")
    assert resp.status_code == 404
