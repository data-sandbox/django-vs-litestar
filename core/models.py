from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""


class Satellite(Base):
    """Persisted satellite record identified by its NORAD catalog ID."""

    __tablename__ = "satellites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    norad_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )

    tle_records: Mapped[list["TleRecord"]] = relationship(
        "TleRecord", back_populates="satellite", cascade="all, delete-orphan"
    )


class TleRecord(Base):
    """Raw TLE data snapshot fetched from the upstream API."""

    __tablename__ = "tle_records"
    __table_args__ = (
        UniqueConstraint("satellite_id", "epoch", name="uq_tle_records_satellite_epoch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    satellite_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("satellites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tle_line1: Mapped[str] = mapped_column(String(69), nullable=False)
    tle_line2: Mapped[str] = mapped_column(String(69), nullable=False)
    epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    satellite: Mapped["Satellite"] = relationship("Satellite", back_populates="tle_records")
    processed: Mapped["ProcessedTle | None"] = relationship(
        "ProcessedTle", back_populates="tle_record", uselist=False, cascade="all, delete-orphan"
    )


class ProcessedTle(Base):
    """Derived orbital parameters computed from a TleRecord via sgp4."""

    __tablename__ = "processed_tle"
    __table_args__ = (UniqueConstraint("tle_record_id", name="uq_processed_tle_tle_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tle_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tle_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    apogee_km: Mapped[float] = mapped_column(Float, nullable=False)
    perigee_km: Mapped[float] = mapped_column(Float, nullable=False)
    inclination_deg: Mapped[float] = mapped_column(Float, nullable=False)
    eccentricity: Mapped[float] = mapped_column(Float, nullable=False)
    mean_motion_rev_per_day: Mapped[float] = mapped_column(Float, nullable=False)
    orbit_type: Mapped[str] = mapped_column(String(10), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    tle_record: Mapped["TleRecord"] = relationship("TleRecord", back_populates="processed")
