import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

# ---------------------------------------------------------------------------
# Sync engine — used by Django, Flask, CLI tools, and Alembic migrations
# ---------------------------------------------------------------------------

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session, committing on exit and rolling back on error."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Async engine — used by FastAPI and Litestar
#
# The URL scheme is changed from postgresql:// (psycopg2) to
# postgresql+asyncpg:// so SQLAlchemy loads the asyncpg driver.  asyncpg
# integrates with the event loop, allowing the ASGI server to handle other
# requests while a query is in flight.
# ---------------------------------------------------------------------------

_async_url = make_url(DATABASE_URL).set(drivername="postgresql+asyncpg")
async_engine = create_async_engine(_async_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional AsyncSession, committing on exit and rolling back on error."""
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
