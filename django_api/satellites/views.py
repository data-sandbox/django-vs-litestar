from datetime import date

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.database import get_session
from core.queries import (
    build_pagination_urls,
    get_satellite_detail,
    get_satellite_history,
    get_satellite_list,
)
from django_api.satellites.serializers import (
    SatelliteDetailSerializer,
    SatelliteListSerializer,
    TleRecordSerializer,
)

_VALID_ORBIT_TYPES = {"LEO", "MEO", "GEO", "HEO", "OTHER"}


def _parse_int_param(request: Request, name: str, default: int, min_val: int, max_val: int) -> int:
    raw = request.query_params.get(name, str(default))
    try:
        val = int(raw)
    except ValueError:
        raise ValidationError({name: f"Must be an integer."})
    if not (min_val <= val <= max_val):
        raise ValidationError({name: f"Must be between {min_val} and {max_val}."})
    return val


class SatelliteListView(APIView):
    def get(self, request: Request) -> Response:
        orbit_type = request.query_params.get("orbit_type") or None
        if orbit_type and orbit_type not in _VALID_ORBIT_TYPES:
            raise ValidationError({"orbit_type": f"Must be one of {sorted(_VALID_ORBIT_TYPES)}."})

        page = _parse_int_param(request, "page", 1, 1, 10_000)
        page_size = _parse_int_param(request, "page_size", 20, 1, 100)

        with get_session() as session:
            count, rows = get_satellite_list(session, orbit_type=orbit_type, page=page, page_size=page_size)

        next_url, prev_url = build_pagination_urls(
            "/api/v1/satellites/", page, page_size, count,
            extra_params={"orbit_type": orbit_type},
        )
        serializer = SatelliteListSerializer(rows, many=True)
        return Response({"count": count, "next": next_url, "previous": prev_url, "results": serializer.data})


class SatelliteDetailView(APIView):
    def get(self, request: Request, norad_id: int) -> Response:
        with get_session() as session:
            row = get_satellite_detail(session, norad_id)

        if row is None:
            raise NotFound(detail=f"Satellite with NORAD ID {norad_id} not found.")

        serializer = SatelliteDetailSerializer(row)
        return Response(serializer.data)


class SatelliteHistoryView(APIView):
    def get(self, request: Request, norad_id: int) -> Response:
        page = _parse_int_param(request, "page", 1, 1, 10_000)
        page_size = _parse_int_param(request, "page_size", 20, 1, 100)

        from_date: date | None = None
        to_date: date | None = None

        if raw := request.query_params.get("from_date"):
            try:
                from_date = date.fromisoformat(raw)
            except ValueError:
                raise ValidationError({"from_date": "Must be an ISO 8601 date (YYYY-MM-DD)."})

        if raw := request.query_params.get("to_date"):
            try:
                to_date = date.fromisoformat(raw)
            except ValueError:
                raise ValidationError({"to_date": "Must be an ISO 8601 date (YYYY-MM-DD)."})

        with get_session() as session:
            exists, count, rows = get_satellite_history(
                session, norad_id, from_date=from_date, to_date=to_date,
                page=page, page_size=page_size,
            )

        if not exists:
            raise NotFound(detail=f"Satellite with NORAD ID {norad_id} not found.")

        next_url, prev_url = build_pagination_urls(
            f"/api/v1/satellites/{norad_id}/history/", page, page_size, count,
            extra_params={"from_date": from_date, "to_date": to_date},
        )
        serializer = TleRecordSerializer(rows, many=True)
        return Response({"count": count, "next": next_url, "previous": prev_url, "results": serializer.data})
