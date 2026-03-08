"""Health check endpoint for DB and Redis connectivity."""

import redis as redis_client
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def health_check(request: object) -> JsonResponse:
    """Check DB and Redis connectivity. Returns JSON with status of each."""
    db_ok = _check_db()
    redis_ok = _check_redis()
    status_code = 200 if (db_ok and redis_ok) else 503

    return JsonResponse(
        {
            "status": "ok" if (db_ok and redis_ok) else "degraded",
            "db": db_ok,
            "redis": redis_ok,
        },
        status=status_code,
    )


def _check_db() -> bool:
    try:
        connection.ensure_connection()
        return True
    except Exception:
        return False


def _check_redis() -> bool:
    try:
        r = redis_client.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]
        return bool(r.ping())
    except Exception:
        return False
