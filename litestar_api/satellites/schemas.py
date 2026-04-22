from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SatelliteListItem(BaseModel):
    """Satellite summary row returned in list responses."""

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
    """Single raw TLE snapshot returned in the history endpoint."""

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
