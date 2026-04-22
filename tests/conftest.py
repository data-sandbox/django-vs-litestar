"""Shared test fixtures for the satellite TLE pipeline test suite.

Start-up order
--------------
1. ``pg_container``   – session-scoped: starts postgres:16 in Docker
2. ``test_engine``    – session-scoped: creates engine, runs Alembic migrations,
                        patches ``core.database`` so ``get_session()`` uses the
                        test DB for the entire pytest run.
3. ``db_session``     – function-scoped: yields a ``Session``; truncates all
                        tables after every test for isolation.
4. Factory fixtures  – function-scoped: factory-boy factories wired to ``db_session``.
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Set DATABASE_URL *before* any core.* import so create_engine() doesn't
# blow up when the .env file isn't available (engine creation is lazy).
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://placeholder:placeholder@localhost:5432/placeholder",
)

import factory  # noqa: E402
import factory.alchemy  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from alembic import command  # noqa: E402
from core.models import ProcessedTle, Satellite, TleRecord  # noqa: E402

# ---------------------------------------------------------------------------
# TLE lines used across multiple tests (ISS-like orbital characteristics)
# ---------------------------------------------------------------------------
ISS_LINE1 = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9999"
ISS_LINE2 = "2 25544  51.6416  95.2778 0006088 342.5427  17.5143 15.49910000000000"

NOAA_LINE1 = "1 33591U 09005A   24001.50000000  .00000000  00000-0  50000-4 0  9998"
NOAA_LINE2 = "2 33591  99.1700 000.0000 0014000  90.0000 270.0000 14.12000000000000"

# ---------------------------------------------------------------------------
# Postgres container (one per pytest session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="session")
def test_engine(pg_container):
    """Create test engine, run migrations, and patch core.database for the session."""
    url = pg_container.get_connection_url()
    engine = create_engine(url, pool_pre_ping=True)

    # alembic/env.py reads DATABASE_URL directly from os.environ, so we must
    # set it to the test container URL before running migrations.
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    # Patch core.database so all code that calls get_session() hits the test DB
    import core.database as db_module

    original_engine = db_module.engine
    original_session_local = db_module.SessionLocal
    db_module.engine = engine
    db_module.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    yield engine

    # Restore after the test session
    db_module.engine = original_engine
    db_module.SessionLocal = original_session_local
    engine.dispose()
    if original_db_url is not None:
        os.environ["DATABASE_URL"] = original_db_url
    else:
        os.environ.pop("DATABASE_URL", None)


# ---------------------------------------------------------------------------
# Per-test session with automatic table truncation
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    session = Session(test_engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        # Truncate in dependency order; RESTART IDENTITY resets serial PKs
        with Session(test_engine) as cleanup:
            cleanup.execute(
                text(
                    "TRUNCATE TABLE processed_tle, tle_records, satellites RESTART IDENTITY CASCADE"
                )
            )
            cleanup.commit()


# ---------------------------------------------------------------------------
# Factory-boy factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def satellite_factory(db_session):
    class _SatelliteFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = Satellite
            sqlalchemy_session = db_session
            sqlalchemy_session_persistence = "commit"

        norad_id = factory.Sequence(lambda n: 10000 + n)
        name = factory.LazyAttribute(lambda o: f"TESTSAT-{o.norad_id}")

    return _SatelliteFactory


@pytest.fixture()
def tle_record_factory(db_session, satellite_factory):
    class _TleRecordFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = TleRecord
            sqlalchemy_session = db_session
            sqlalchemy_session_persistence = "commit"

        satellite = factory.SubFactory(satellite_factory)
        satellite_id = factory.SelfAttribute("satellite.id")
        tle_line1 = ISS_LINE1
        tle_line2 = ISS_LINE2
        epoch = factory.LazyFunction(lambda: datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC))
        fetched_at = factory.LazyFunction(lambda: datetime.now(UTC))

    return _TleRecordFactory


@pytest.fixture()
def processed_tle_factory(db_session, tle_record_factory):
    class _ProcessedTleFactory(factory.alchemy.SQLAlchemyModelFactory):
        class Meta:
            model = ProcessedTle
            sqlalchemy_session = db_session
            sqlalchemy_session_persistence = "commit"

        tle_record = factory.SubFactory(tle_record_factory)
        tle_record_id = factory.SelfAttribute("tle_record.id")
        period_minutes = 92.65
        apogee_km = 420.0
        perigee_km = 410.0
        inclination_deg = 51.64
        eccentricity = 0.0006088
        mean_motion_rev_per_day = 15.499
        orbit_type = "LEO"

    return _ProcessedTleFactory


# ---------------------------------------------------------------------------
# Helper: make a patched get_session() that yields the given db_session
# ---------------------------------------------------------------------------


def make_patch_get_session(session: Session):
    """Return a drop-in replacement for ``get_session()`` that yields *session*."""

    @contextmanager
    def _patched():
        yield session

    return _patched
