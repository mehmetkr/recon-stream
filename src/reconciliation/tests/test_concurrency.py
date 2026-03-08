"""Concurrency tests for the matching engine.

Uses ThreadPoolExecutor to simulate concurrent reconciliation runs
and verify that select_for_update(skip_locked=True) prevents
duplicate MatchResults.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from django.db import close_old_connections

from reconciliation.models import MatchResult, ReconciliationJob
from reconciliation.services.matcher import ReconciliationMatcher
from reconciliation.tests.factories import (
    BankTransactionFactory,
    GLEntryFactory,
    ReconciliationJobFactory,
)


def _run_matcher(job_id: str) -> dict:  # type: ignore[type-arg]
    """Run matcher in a separate thread."""
    close_old_connections()  # Each thread needs its own DB connection
    job = ReconciliationJob.objects.get(id=job_id)
    matcher = ReconciliationMatcher(job)
    return matcher.run()


@pytest.mark.django_db(transaction=True)
def test_concurrent_matching_no_duplicates() -> None:
    """Multiple threads reconciling the same job should never create duplicates.

    This validates that select_for_update(skip_locked=True) works correctly
    to prevent two threads from matching the same GL entry.
    """
    job = ReconciliationJobFactory()

    # Create 20 exact-matchable pairs
    for i in range(20):
        BankTransactionFactory(
            job=job,
            external_id=f"CONC-BANK-{i}",
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference=f"REF-{i:04d}",
            description=f"Test Transaction {i}",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference=f"REF-{i:04d}",
            description=f"Test Payment {i}",
        )

    # Run matcher from 5 threads concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_run_matcher, str(job.id)) for _ in range(5)]
        for f in futures:
            f.result()

    # Verify: exactly 20 matches, no duplicates
    total_matches = MatchResult.objects.filter(job=job).count()
    assert total_matches == 20, f"Expected 20 matches, got {total_matches}"

    # Verify no GL entry is matched more than once
    from django.db.models import Count

    duplicates = (
        MatchResult.objects.filter(job=job)
        .values("gl_entry")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    assert duplicates.count() == 0, f"Found duplicate matches: {list(duplicates)}"
