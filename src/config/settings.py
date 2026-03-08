"""Django settings for ReconStream project."""

import os
from pathlib import Path

import environ

from core.logging import get_logging_config

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent.parent  # src/
PROJECT_ROOT = BASE_DIR.parent  # recon-stream/

# ---------- Environment ----------
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:8000"]),
)

# Read .env file from project root
env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.isfile(env_file):
    environ.Env.read_env(env_file)

# ---------- Security ----------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS: list[str] = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS: list[str] = env("DJANGO_CSRF_TRUSTED_ORIGINS")

# ---------- Application definition ----------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Project apps
    "core",
    "reconciliation",
]

MIDDLEWARE = [
    "core.middleware.request_id.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.idempotency.IdempotencyMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------- Database ----------
DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- Auth ----------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- Internationalization ----------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------- Static files ----------
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(PROJECT_ROOT, "staticfiles")

# ---------- Redis ----------
REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

# ---------- Celery ----------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ---------- Logging ----------
LOGGING = get_logging_config(debug=DEBUG)
