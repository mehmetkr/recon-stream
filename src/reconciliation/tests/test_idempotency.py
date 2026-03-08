"""Tests for idempotency middleware."""

import pytest
import redis as redis_client
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import Client


@pytest.fixture(autouse=True)
def _flush_redis():
    """Clear Redis idempotency keys before each test."""
    r = redis_client.from_url(settings.REDIS_URL)
    # Only delete idempotency keys, not everything
    for key in r.scan_iter("idempotency:*"):
        r.delete(key)
    yield
    for key in r.scan_iter("idempotency:*"):
        r.delete(key)


class TestIdempotencyMiddleware:
    def test_same_key_returns_cached_response(self, client: Client) -> None:
        """Same Idempotency-Key should return cached response without re-processing."""
        csv_content = b"external_id,date,amount,description,reference\nTXN-001,2024-01-15,100.50,Starbucks,REF-001\n"
        key = "test-idem-key-001"

        # First request
        file1 = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        response1 = client.post(
            "/api/upload/bank-transactions/",
            {"file": file1},
            HTTP_IDEMPOTENCY_KEY=key,
        )
        assert response1.status_code == 201

        # Second request with same key — should return cached response
        file2 = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        response2 = client.post(
            "/api/upload/bank-transactions/",
            {"file": file2},
            HTTP_IDEMPOTENCY_KEY=key,
        )
        assert response2.status_code == 201

        # Verify same job_id returned (cached)
        import json
        body1 = json.loads(response1.content)
        body2 = json.loads(response2.content)
        assert body1["job_id"] == body2["job_id"]

    def test_different_keys_process_separately(self, client: Client) -> None:
        """Different Idempotency-Keys should each be processed independently."""
        csv_content = b"external_id,date,amount,description,reference\nTXN-001,2024-01-15,100.50,Starbucks,REF-001\n"

        file1 = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        response1 = client.post(
            "/api/upload/bank-transactions/",
            {"file": file1},
            HTTP_IDEMPOTENCY_KEY="key-A",
        )

        file2 = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        response2 = client.post(
            "/api/upload/bank-transactions/",
            {"file": file2},
            HTTP_IDEMPOTENCY_KEY="key-B",
        )

        assert response1.status_code == 201
        assert response2.status_code == 201

        import json
        body1 = json.loads(response1.content)
        body2 = json.loads(response2.content)
        # Different keys should create different jobs
        assert body1["job_id"] != body2["job_id"]

    def test_no_key_processes_normally(self, client: Client) -> None:
        """Requests without Idempotency-Key should be processed normally every time."""
        csv_content = b"external_id,date,amount,description,reference\nTXN-001,2024-01-15,100.50,Starbucks,REF-001\n"

        file1 = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        response1 = client.post(
            "/api/upload/bank-transactions/",
            {"file": file1},
        )

        file2 = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        response2 = client.post(
            "/api/upload/bank-transactions/",
            {"file": file2},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201

        import json
        body1 = json.loads(response1.content)
        body2 = json.loads(response2.content)
        assert body1["job_id"] != body2["job_id"]
