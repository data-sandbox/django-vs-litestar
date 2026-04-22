from rest_framework import serializers


class SatelliteListSerializer(serializers.Serializer):
    """Serializer for satellite list items with latest processed orbital parameters."""

    norad_id = serializers.IntegerField()
    name = serializers.CharField()
    orbit_type = serializers.CharField()
    period_minutes = serializers.FloatField()
    apogee_km = serializers.FloatField()
    perigee_km = serializers.FloatField()
    inclination_deg = serializers.FloatField()
    last_updated = serializers.DateTimeField()


class SatelliteDetailSerializer(serializers.Serializer):
    """Serializer for the full satellite detail response including eccentricity and mean motion."""

    norad_id = serializers.IntegerField()
    name = serializers.CharField()
    orbit_type = serializers.CharField()
    period_minutes = serializers.FloatField()
    apogee_km = serializers.FloatField()
    perigee_km = serializers.FloatField()
    inclination_deg = serializers.FloatField()
    eccentricity = serializers.FloatField()
    mean_motion_rev_per_day = serializers.FloatField()
    last_updated = serializers.DateTimeField()


class TleRecordSerializer(serializers.Serializer):
    """Serializer for a single raw TLE record in the history endpoint."""

    tle_line1 = serializers.CharField()
    tle_line2 = serializers.CharField()
    epoch = serializers.DateTimeField()
    fetched_at = serializers.DateTimeField()
