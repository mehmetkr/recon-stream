"""Two-pass reconciliation matching engine.

Pass 1: Exact match via SQL (amount + date + reference).
Pass 2: Fuzzy match via PostgreSQL pg_trgm trigram similarity.
"""

import time
from datetime import timedelta
from decimal import Decimal

import structlog
from django.contrib.postgres.search import TrigramSimilarity
from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery

from reconciliation.models import (
    BankTransaction,
    GLEntry,
    MatchResult,
    ReconciliationJob,
)

log = structlog.get_logger("reconciliation.matcher")

# Fuzzy matching thresholds
AMOUNT_TOLERANCE = Decimal("0.10")
DATE_WINDOW_DAYS = 5
SIMILARITY_THRESHOLD = 0.3


class ReconciliationMatcher:
    """Standalone matching service — no HTTP dependencies."""

    def __init__(self, job: ReconciliationJob) -> None:
        self.job = job
        self._log = log.bind(job_id=str(job.id))

    def run(self) -> dict:  # type: ignore[type-arg]
        """Execute both matching passes and return stats."""
        self._log.info("reconciliation_started")
        start = time.monotonic()

        exact_count = self._exact_match_pass()
        fuzzy_count = self._fuzzy_match_pass()

        duration_ms = int((time.monotonic() - start) * 1000)

        total_bank = BankTransaction.objects.filter(job=self.job).count()
        total_gl = GLEntry.objects.filter(job=self.job).count()
        unmatched_bank = (
            BankTransaction.objects.filter(job=self.job).unmatched().count()
        )
        unmatched_gl = (
            GLEntry.objects.filter(job=self.job).unmatched().count()
        )

        stats = {
            "total_bank_transactions": total_bank,
            "total_gl_entries": total_gl,
            "exact_matches": exact_count,
            "fuzzy_matches": fuzzy_count,
            "unmatched_bank_transactions": unmatched_bank,
            "unmatched_gl_entries": unmatched_gl,
            "duration_ms": duration_ms,
        }

        # Persist stats on the job
        self.job.stats = stats
        self.job.save(update_fields=["stats", "updated_at"])

        self._log.info("reconciliation_completed", **stats)
        return stats

    def _exact_match_pass(self) -> int:
        """Match on amount + date + reference (SQL-native, no Python iteration).

        Uses a Subquery to find the first unmatched GLEntry that matches
        each unmatched BankTransaction on amount, date, and reference.
        Lock acquisition and insert happen in the same atomic block to
        ensure the row lock is held until the MatchResult is committed.
        """
        matches_qs = (
            BankTransaction.objects.filter(job=self.job)
            .unmatched()
            .annotate(
                gl_match_id=Subquery(
                    GLEntry.objects.filter(job=self.job)
                    .unmatched()
                    .filter(
                        amount=OuterRef("amount"),
                        date=OuterRef("date"),
                        reference=OuterRef("reference"),
                    )
                    .values("id")[:1]
                )
            )
            .filter(gl_match_id__isnull=False)
        )

        count = 0
        for bank_tx in matches_qs:
            try:
                with transaction.atomic():
                    # Lock by ID only (no outer join — PG forbids FOR UPDATE
                    # on nullable side), then verify unmatched under lock.
                    gl_entry = (
                        GLEntry.objects.select_for_update(skip_locked=True)
                        .filter(id=bank_tx.gl_match_id)
                        .first()
                    )
                    if gl_entry is None:
                        continue
                    if MatchResult.objects.filter(gl_entry=gl_entry).exists():
                        continue
                    MatchResult.objects.create(
                        job=self.job,
                        bank_transaction=bank_tx,
                        gl_entry=gl_entry,
                        match_type=MatchResult.MatchType.EXACT,
                        confidence=Decimal("1.0000"),
                        matched_on=["amount", "date", "reference"],
                    )
                    count += 1
            except IntegrityError:
                continue

        return count

    def _fuzzy_match_pass(self) -> int:
        """Match unmatched rows using pg_trgm trigram similarity.

        Narrows candidates by amount tolerance and date window,
        then ranks by description similarity. Lock and insert share
        a single atomic block to prevent race conditions.
        """
        unmatched_bank_txs = BankTransaction.objects.filter(job=self.job).unmatched()

        count = 0
        for bank_tx in unmatched_bank_txs.iterator():
            candidates = (
                GLEntry.objects.filter(job=self.job)
                .unmatched()
                .filter(
                    date__range=(
                        bank_tx.date - timedelta(days=DATE_WINDOW_DAYS),
                        bank_tx.date + timedelta(days=DATE_WINDOW_DAYS),
                    ),
                    amount__range=(
                        bank_tx.amount - AMOUNT_TOLERANCE,
                        bank_tx.amount + AMOUNT_TOLERANCE,
                    ),
                )
                .annotate(
                    similarity=TrigramSimilarity("description", bank_tx.description)
                )
                .filter(similarity__gt=SIMILARITY_THRESHOLD)
                .order_by("-similarity")
            )

            best = candidates.first()
            if best is None:
                continue

            try:
                with transaction.atomic():
                    gl_entry = (
                        GLEntry.objects.select_for_update(skip_locked=True)
                        .filter(id=best.id)
                        .first()
                    )
                    if gl_entry is None:
                        continue
                    if MatchResult.objects.filter(gl_entry=gl_entry).exists():
                        continue
                    MatchResult.objects.create(
                        job=self.job,
                        bank_transaction=bank_tx,
                        gl_entry=gl_entry,
                        match_type=MatchResult.MatchType.FUZZY,
                        confidence=Decimal(str(round(best.similarity, 4))),
                        matched_on=["amount_range", "date_range", "description_similarity"],
                    )
                    count += 1
            except IntegrityError:
                continue

        return count
