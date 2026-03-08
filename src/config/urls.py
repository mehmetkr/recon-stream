"""URL configuration for ReconStream project."""

from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from core.health import health_check
from reconciliation.api import router as reconciliation_router

api = NinjaAPI(
    title="ReconStream API",
    version="0.1.0",
    description="High-volume bank reconciliation engine",
)
api.add_router("", reconciliation_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("health/", health_check),
]
