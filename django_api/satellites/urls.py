from django.urls import path

from django_api.satellites.views import (
    SatelliteDetailView,
    SatelliteHistoryView,
    SatelliteListView,
)

urlpatterns = [
    path("satellites/", SatelliteListView.as_view(), name="satellite-list"),
    path(
        "satellites/<int:norad_id>/",
        SatelliteDetailView.as_view(),
        name="satellite-detail",
    ),
    path(
        "satellites/<int:norad_id>/history/",
        SatelliteHistoryView.as_view(),
        name="satellite-history",
    ),
]
