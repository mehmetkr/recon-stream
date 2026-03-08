"""Query count regression tests to prevent N+1 issues."""

from datetime import date
from decimal import Decimal

import pytest
from django.test.client import Client

from reconciliation.models import MatchResult, ReconciliationJob
from reconciliation.tests.factories import (
    BankTransactionFactory,
    GLEntryFactory,
    ReconciliationJobFactory,
)


@pytest.fixture()
def seeded_job():
    """Create a job with matches for query count testing."""
    job = ReconciliationJobFactory()
    for i in range(10):
        bank_tx = BankTransactionFactory(
            job=job,
            external_id=f"QC-{i}",
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
        )
        gl_entry = GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
        )
        MatchResult.objects.create(
            job=job,
            bank_transaction=bank_tx,
            gl_entry=gl_entry,
            match_type=MatchResult.MatchType.EXACT,
            confidence=Decimal("1.0000"),
            matched_on=["amount", "date", "reference"],
        )
    return job


@pytest.mark.django_db()
def test_results_endpoint_query_count(
    client: Client,
    django_assert_num_queries: pytest.FixtureRequest,  # type: ignore[type-arg]
    seeded_job,
) -> None:
    """Results endpoint should use a bounded number of queries regardless of result count.

    Expected queries:
    1. Get job (get_object_or_404)
    2. Count matches
    3. Fetch matches with select_related (bank_transaction, gl_entry)
    """
    # ATOMIC_REQUESTS adds SAVEPOINT + RELEASE SAVEPOINT = 2 extra queries
    # 1. SAVEPOINT
    # 2. SELECT job (get_object_or_404)
    # 3. COUNT matches
    # 4. SELECT matches with select_related
    # 5. RELEASE SAVEPOINT
    with django_assert_num_queries(5):
        response = client.get(f"/api/results/{seeded_job.id}/")
    assert response.status_code == 200


@pytest.mark.django_db()
def test_stats_endpoint_uses_cached_data_for_completed_job(
    client: Client,
    django_assert_num_queries: pytest.FixtureRequest,  # type: ignore[type-arg]
) -> None:
    """Completed jobs should return cached stats without COUNT queries.

    Expected queries:
    1. SAVEPOINT
    2. SELECT job (get_object_or_404)
    3. RELEASE SAVEPOINT
    """
    job = ReconciliationJobFactory(
        status=ReconciliationJob.Status.COMPLETED,
        stats={
            "total_bank_transactions": 10,
            "total_gl_entries": 10,
            "exact_matches": 8,
            "fuzzy_matches": 2,
            "unmatched_bank_transactions": 0,
            "unmatched_gl_entries": 0,
            "duration_ms": 120,
        },
    )
    with django_assert_num_queries(3):
        response = client.get(f"/api/stats/{job.id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["exact_matches"] == 8
    assert data["fuzzy_matches"] == 2
