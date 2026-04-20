from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SatelliteListItem(BaseModel):
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
    count: int
    next: str | None
    previous: str | None
    results: list[SatelliteListItem]


class SatelliteDetail(BaseModel):
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
    model_config = ConfigDict(from_attributes=True)

    tle_line1: str
    tle_line2: str
    epoch: datetime
    fetched_at: datetime


class TleHistoryResponse(BaseModel):
    count: int
    next: str | None
    previous: str | None
    results: list[TleHistoryItem]
