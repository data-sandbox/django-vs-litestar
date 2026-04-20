import os

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-in-production")
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "drf_spectacular",
    "django_api.satellites",
]

DATABASES = {}  # Django ORM disabled; all DB access via SQLAlchemy

ROOT_URLCONF = "django_api.config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "/static/"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DATETIME_FORMAT": "iso-8601",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Satellite TLE API (Django + DRF)",
    "DESCRIPTION": (
        "Read-only REST API for satellite TLE orbital data. "
        "Django implementation — compare with the Litestar version at :8001."
    ),
    "VERSION": "1.0.0",
}
