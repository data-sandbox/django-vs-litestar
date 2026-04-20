"""Tests for core/processing.py – orbital calculations and batch processing."""

import math
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from core.models import ProcessedTle
from core.processing import classify_orbit, compute_orbital_params, process_unprocessed
from tests.conftest import ISS_LINE1, ISS_LINE2

# ---------------------------------------------------------------------------
# compute_orbital_params – unit tests
# ---------------------------------------------------------------------------


def test_orbital_params_returns_required_keys():
    params = compute_orbital_params(ISS_LINE1, ISS_LINE2)
    expected_keys = {
        "period_minutes",
        "apogee_km",
        "perigee_km",
        "inclination_deg",
        "eccentricity",
        "mean_motion_rev_per_day",
    }
    assert expected_keys == set(params.keys())


def test_orbital_params_iss_period():
    """ISS mean motion is ~15.5 rev/day → period ~92–93 minutes."""
    params = compute_orbital_params(ISS_LINE1, ISS_LINE2)
    assert 90.0 < params["period_minutes"] < 96.0, params["period_minutes"]


def test_orbital_params_iss_altitude():
    """ISS orbits at 400–450 km altitude."""
    params = compute_orbital_params(ISS_LINE1, ISS_LINE2)
    assert 380.0 < params["perigee_km"] < 480.0, params["perigee_km"]
    assert 380.0 < params["apogee_km"] < 480.0, params["apogee_km"]


def test_orbital_params_iss_inclination():
    """ISS inclination is approximately 51.64°."""
    params = compute_orbital_params(ISS_LINE1, ISS_LINE2)
    assert abs(params["inclination_deg"] - 51.64) < 0.1, params["inclination_deg"]


def test_orbital_params_iss_eccentricity():
    """ISS TLE has eccentricity ~0.0006088."""
    params = compute_orbital_params(ISS_LINE1, ISS_LINE2)
    assert abs(params["eccentricity"] - 0.0006088) < 1e-5, params["eccentricity"]


def test_period_mean_motion_consistency():
    """period_minutes × mean_motion_rev_per_day should equal 1440."""
    params = compute_orbital_params(ISS_LINE1, ISS_LINE2)
    product = params["period_minutes"] * params["mean_motion_rev_per_day"]
    assert abs(product - 1440.0) < 0.01, product


# ---------------------------------------------------------------------------
# classify_orbit – boundary-value tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "apogee, perigee, eccentricity, expected",
    [
        # HEO – high eccentricity
        (50_000.0, 500.0, 0.8, "HEO"),
        # GEO – ~35,786 km circular
        (35_786.0, 35_786.0, 0.0001, "GEO"),
        # LEO – low altitude circular
        (420.0, 400.0, 0.0006, "LEO"),
        # MEO – GPS-like orbit
        (20_200.0, 20_000.0, 0.001, "MEO"),
        # OTHER – above GEO altitude band
        (42_000.0, 42_000.0, 0.001, "OTHER"),
    ],
)
def test_classify_orbit(apogee, perigee, eccentricity, expected):
    assert classify_orbit(apogee, perigee, eccentricity) == expected


# ---------------------------------------------------------------------------
# process_unprocessed – integration tests against real Postgres
# ---------------------------------------------------------------------------


def test_process_unprocessed_happy_path(db_session, tle_record_factory):
    """Unprocessed TLE records should be processed and results persisted."""
    tle_record_factory()  # creates satellite + tle_record with ISS TLE lines

    result = process_unprocessed(db_session)
    db_session.commit()

    assert result["processed"] == 1
    assert result["errors"] == 0

    processed = db_session.execute(select(ProcessedTle)).scalars().all()
    assert len(processed) == 1
    p = processed[0]
    assert p.orbit_type == "LEO"
    assert 90.0 < p.period_minutes < 96.0
    assert p.inclination_deg > 50.0


def test_process_unprocessed_idempotent(db_session, tle_record_factory):
    """Running process_unprocessed twice must not create duplicate ProcessedTle rows."""
    tle_record_factory()

    process_unprocessed(db_session)
    db_session.commit()

    result = process_unprocessed(db_session)
    db_session.commit()

    assert result["processed"] == 0
    assert result["errors"] == 0

    processed = db_session.execute(select(ProcessedTle)).scalars().all()
    assert len(processed) == 1


def test_process_unprocessed_multiple_records(db_session, tle_record_factory, satellite_factory):
    """All unprocessed records across different satellites are handled."""
    sat2 = satellite_factory(norad_id=33591, name="NOAA 19")
    tle_record_factory()  # ISS
    tle_record_factory(satellite=sat2, satellite_id=sat2.id)  # NOAA 19

    result = process_unprocessed(db_session)
    db_session.commit()

    assert result["processed"] == 2
    assert result["errors"] == 0
