"""Marshmallow schemas for the Flask satellite API."""

import marshmallow as ma


class SatelliteListQuerySchema(ma.Schema):
    """Query parameters for the satellite list endpoint."""

    orbit_type = ma.fields.Str(load_default=None, allow_none=True)
    page = ma.fields.Int(load_default=1, validate=ma.validate.Range(min=1))
    page_size = ma.fields.Int(load_default=20, validate=ma.validate.Range(min=1, max=100))

    @ma.validates("orbit_type")
    def validate_orbit_type(self, value: str | None, **kwargs: object) -> None:
        """Reject orbit_type values not in the allowed set."""
        valid = {"LEO", "MEO", "GEO", "HEO", "OTHER"}
        if value is not None and value not in valid:
            raise ma.ValidationError(f"Must be one of {sorted(valid)}.")


class SatelliteListItemSchema(ma.Schema):
    """Schema for a single satellite in the list response."""

    norad_id = ma.fields.Int()
    name = ma.fields.Str()
    orbit_type = ma.fields.Str()
    period_minutes = ma.fields.Float()
    apogee_km = ma.fields.Float()
    perigee_km = ma.fields.Float()
    inclination_deg = ma.fields.Float()
    last_updated = ma.fields.DateTime()


class SatelliteListResponseSchema(ma.Schema):
    """Paginated envelope wrapping a list of SatelliteListItem records."""

    count = ma.fields.Int()
    next = ma.fields.Str(allow_none=True)
    previous = ma.fields.Str(allow_none=True)
    results = ma.fields.List(ma.fields.Nested(SatelliteListItemSchema))


class SatelliteDetailSchema(ma.Schema):
    """Full orbital detail for a single satellite including eccentricity and mean motion."""

    norad_id = ma.fields.Int()
    name = ma.fields.Str()
    orbit_type = ma.fields.Str()
    period_minutes = ma.fields.Float()
    apogee_km = ma.fields.Float()
    perigee_km = ma.fields.Float()
    inclination_deg = ma.fields.Float()
    eccentricity = ma.fields.Float()
    mean_motion_rev_per_day = ma.fields.Float()
    last_updated = ma.fields.DateTime()


class TleHistoryQuerySchema(ma.Schema):
    """Query parameters for the TLE history endpoint."""

    page = ma.fields.Int(load_default=1, validate=ma.validate.Range(min=1))
    page_size = ma.fields.Int(load_default=20, validate=ma.validate.Range(min=1, max=100))
    from_date = ma.fields.Date(load_default=None, allow_none=True)
    to_date = ma.fields.Date(load_default=None, allow_none=True)


class TleHistoryItemSchema(ma.Schema):
    """Schema for a single raw TLE snapshot in the history response."""

    tle_line1 = ma.fields.Str()
    tle_line2 = ma.fields.Str()
    epoch = ma.fields.DateTime()
    fetched_at = ma.fields.DateTime()


class TleHistoryResponseSchema(ma.Schema):
    """Paginated envelope wrapping a list of TleHistoryItem records."""

    count = ma.fields.Int()
    next = ma.fields.Str(allow_none=True)
    previous = ma.fields.Str(allow_none=True)
    results = ma.fields.List(ma.fields.Nested(TleHistoryItemSchema))
