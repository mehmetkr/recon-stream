"""Request ID middleware for request tracing.

Generates a UUID for each request and adds it to:
- Response headers (X-Request-ID)
- Thread-local context for use in structured logging.
"""

import uuid
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

# Context variable for request ID — accessible from anywhere in the same async context
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdMiddleware:
    def __init__(self, get_response):  # type: ignore[no-untyped-def]
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(rid)

        response: HttpResponse = self.get_response(request)
        response["X-Request-ID"] = rid

        return response
