"""Pydantic schemas for the Flask satellite API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_OrbitType = Literal["LEO", "MEO", "GEO", "HEO", "OTHER"]


# ── Query parameter models ────────────────────────────────────────────────────


class SatelliteListQuery(BaseModel):
    """Query parameters for the satellite list endpoint."""

    orbit_type: _OrbitType | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class TleHistoryQuery(BaseModel):
    """Query parameters for the TLE history endpoint."""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    from_date: date | None = None
    to_date: date | None = None


# ── Response models ───────────────────────────────────────────────────────────


class SatelliteListItem(BaseModel):
    """A single satellite in the list response."""

    model_config = ConfigDict(from_attributes=True)

    norad_id: int
    name: str
    orbit_type: str
    period_minutes: float
    apogee_km: float
    perigee_km: float
    inclination_deg: float
    last_updated: datetime


class SatelliteListResponse(BaseModel):
    """Paginated envelope wrapping a list of SatelliteListItem records."""

    count: int
    next: str | None
    previous: str | None
    results: list[SatelliteListItem]


class SatelliteDetail(BaseModel):
    """Full orbital detail for a single satellite including eccentricity and mean motion."""

    model_config = ConfigDict(from_attributes=True)

    norad_id: int
    name: str
    orbit_type: str
    period_minutes: float
    apogee_km: float
    perigee_km: float
    inclination_deg: float
    eccentricity: float
    mean_motion_rev_per_day: float
    last_updated: datetime


class TleHistoryItem(BaseModel):
    """A single raw TLE snapshot in the history response."""

    model_config = ConfigDict(from_attributes=True)

    tle_line1: str
    tle_line2: str
    epoch: datetime
    fetched_at: datetime


class TleHistoryResponse(BaseModel):
    """Paginated envelope wrapping a list of TleHistoryItem records."""

    count: int
    next: str | None
    previous: str | None
    results: list[TleHistoryItem]
