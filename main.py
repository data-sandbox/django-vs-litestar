import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import click
from dotenv import load_dotenv

load_dotenv()


@click.group()
def cli() -> None:
    """Satellite TLE pipeline CLI."""


@cli.command("start-db")
def start_db() -> None:
    """Start the PostgreSQL container via docker compose."""
    from core.logging_config import setup_logging

    setup_logging()
    subprocess.run(["docker", "compose", "up", "-d"], check=True)


@cli.command("stop-db")
def stop_db() -> None:
    """Stop the PostgreSQL container via docker compose."""
    from core.logging_config import setup_logging

    setup_logging()
    subprocess.run(["docker", "compose", "down"], check=True)


@cli.command("migrate")
def migrate() -> None:
    """Apply Alembic migrations to the database."""
    from core.logging_config import setup_logging

    setup_logging()
    from alembic import command as alembic_command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_command.upgrade(alembic_cfg, "head")


@cli.command("ingest")
def ingest() -> None:
    """Fetch current TLE data for both satellites and persist to the database."""
    import logging

    from core.database import get_session
    from core.ingestion import ingest_satellites
    from core.logging_config import setup_logging

    setup_logging()
    logger = logging.getLogger(__name__)

    with get_session() as session:
        result = ingest_satellites(session)
    logger.info("ingest complete", extra=result)


@cli.command("backfill")
def backfill() -> None:
    """Simulate BACKFILL_DAYS days of TLE history (runs ingest with backdated fetched_at)."""
    import logging

    from core.database import get_session
    from core.ingestion import ingest_satellites
    from core.logging_config import setup_logging

    setup_logging()
    logger = logging.getLogger(__name__)
    days = int(os.environ.get("BACKFILL_DAYS", "7"))

    for day in range(days):
        fetched_at = datetime.now(timezone.utc) - timedelta(days=day)
        with get_session() as session:
            result = ingest_satellites(
                session,
                fetched_at=fetched_at,
                epoch_offset=timedelta(days=day),
            )
        logger.info("backfill day complete", extra={"day": day, **result})


@cli.command("process")
def process() -> None:
    """Compute orbital parameters for all unprocessed TLE records."""
    from core.database import get_session
    from core.logging_config import setup_logging
    from core.processing import process_unprocessed

    setup_logging()
    with get_session() as session:
        process_unprocessed(session)


@cli.command("run-django")
def run_django() -> None:
    """Start the Django development server (blocking)."""
    from core.logging_config import setup_logging

    setup_logging()
    host = os.environ.get("DJANGO_HOST", "127.0.0.1")
    port = os.environ.get("DJANGO_PORT", "8000")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.config.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "runserver", f"{host}:{port}"])


@cli.command("run-litestar")
def run_litestar() -> None:
    """Start the Litestar development server (blocking)."""
    from core.logging_config import setup_logging

    setup_logging()
    import uvicorn

    host = os.environ.get("LITESTAR_HOST", "127.0.0.1")
    port = int(os.environ.get("LITESTAR_PORT", "8001"))
    uvicorn.run("litestar_api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    cli()

