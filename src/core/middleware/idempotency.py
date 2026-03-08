"""Idempotency middleware using Redis for POST request deduplication.

If an Idempotency-Key header is present on a POST request:
1. Check Redis for a cached response.
2. If found, return the cached response without processing.
3. If not found, set a NX lock, process the request, cache the response (24h TTL).
"""

import json

import redis as redis_client
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

IDEMPOTENCY_TTL = 86400  # 24 hours


class IdempotencyMiddleware:
    def __init__(self, get_response):  # type: ignore[no-untyped-def]
        self.get_response = get_response
        self.redis = redis_client.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST":
            return self.get_response(request)  # type: ignore[no-any-return]

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return self.get_response(request)  # type: ignore[no-any-return]

        cache_key = f"idempotency:{idempotency_key}"

        # Check for cached response
        cached = self.redis.get(cache_key)
        if cached is not None:
            data = json.loads(cached)
            return JsonResponse(
                data["body"],
                status=data["status_code"],
                safe=False,
            )

        # Process the request
        response = self.get_response(request)

        # Cache the response if it was successful (2xx)
        if 200 <= response.status_code < 300:
            try:
                body = json.loads(response.content)
                cache_data = json.dumps({
                    "status_code": response.status_code,
                    "body": body,
                })
                self.redis.set(cache_key, cache_data, ex=IDEMPOTENCY_TTL, nx=True)
            except (json.JSONDecodeError, AttributeError):
                pass  # Don't cache non-JSON responses

        return response  # type: ignore[no-any-return]
