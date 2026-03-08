"""Tests for the two-pass reconciliation matching engine."""

from datetime import date, timedelta
from decimal import Decimal

from freezegun import freeze_time

from reconciliation.models import MatchResult
from reconciliation.services.matcher import DATE_WINDOW_DAYS, ReconciliationMatcher
from reconciliation.tests.factories import (
    BankTransactionFactory,
    GLEntryFactory,
    ReconciliationJobFactory,
)


class TestExactMatching:
    def test_exact_match_on_amount_date_reference(self) -> None:
        """Identical amount, date, and reference should produce an EXACT match."""
        job = ReconciliationJobFactory()
        bank_tx = BankTransactionFactory(
            job=job,
            amount=Decimal("100.50"),
            date=date(2024, 1, 15),
            reference="REF-001",
            description="Starbucks Coffee #123",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.50"),
            date=date(2024, 1, 15),
            reference="REF-001",
            description="Starbucks Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["exact_matches"] == 1
        match = MatchResult.objects.get(bank_transaction=bank_tx)
        assert match.match_type == "EXACT"
        assert match.confidence == Decimal("1.0000")

    def test_no_match_when_amount_differs(self) -> None:
        """Different amounts should NOT produce an exact match."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("100.50"),
            date=date(2024, 1, 15),
            reference="REF-001",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("200.00"),
            date=date(2024, 1, 15),
            reference="REF-001",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["exact_matches"] == 0

    def test_no_duplicate_matches(self) -> None:
        """Running matcher twice should not create duplicate matches."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference="REF-001",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference="REF-001",
        )

        matcher = ReconciliationMatcher(job)
        matcher.run()
        stats = matcher.run()  # Second run

        assert MatchResult.objects.filter(job=job).count() == 1
        assert stats["exact_matches"] == 0  # No new matches on second run


class TestFuzzyMatching:
    def test_fuzzy_match_similar_description(self) -> None:
        """Similar descriptions within amount/date tolerance should fuzzy match."""
        job = ReconciliationJobFactory()
        bank_tx = BankTransactionFactory(
            job=job,
            amount=Decimal("100.50"),
            date=date(2024, 1, 15),
            reference="",
            description="Starbucks Coffee #123",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.50"),
            date=date(2024, 1, 15),
            reference="DIFFERENT-REF",  # Different ref prevents exact match
            description="Starbucks Coffee Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["exact_matches"] == 0  # Refs differ
        assert stats["fuzzy_matches"] == 1
        match = MatchResult.objects.get(bank_transaction=bank_tx)
        assert match.match_type == "FUZZY"
        assert match.confidence > Decimal("0.3")

    def test_fuzzy_match_within_date_window(self) -> None:
        """Dates within 5-day window should still be candidates for fuzzy match."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("500.00"),
            date=date(2024, 1, 15),
            reference="",
            description="Amazon Web Services Monthly",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("500.00"),
            date=date(2024, 1, 18),  # 3 days later
            reference="DIFFERENT",
            description="Amazon Web Services Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 1

    def test_no_fuzzy_match_when_amount_too_different(self) -> None:
        """Amounts outside tolerance should NOT produce a fuzzy match."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference="",
            description="Starbucks Coffee",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("200.00"),  # Way too different
            date=date(2024, 1, 15),
            reference="DIFFERENT",
            description="Starbucks Coffee Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 0

    def test_no_fuzzy_match_outside_date_window(self) -> None:
        """Dates outside 5-day window should NOT be candidates."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 1),
            reference="",
            description="Starbucks Coffee",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 20),  # 19 days later
            reference="DIFFERENT",
            description="Starbucks Coffee Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 0


class TestMixedMatching:
    def test_exact_matches_before_fuzzy(self) -> None:
        """Exact pass should run first; fuzzy pass operates on remaining unmatched."""
        job = ReconciliationJobFactory()

        # This pair will exact-match
        BankTransactionFactory(
            job=job,
            external_id="EXACT-1",
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference="REF-001",
            description="Starbucks Coffee",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 1, 15),
            reference="REF-001",
            description="Starbucks Payment",
        )

        # This pair will fuzzy-match
        BankTransactionFactory(
            job=job,
            external_id="FUZZY-1",
            amount=Decimal("250.00"),
            date=date(2024, 1, 16),
            reference="",
            description="Amazon Web Services Monthly",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("250.00"),
            date=date(2024, 1, 16),
            reference="DIFFERENT",
            description="Amazon Web Services Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["exact_matches"] == 1
        assert stats["fuzzy_matches"] == 1
        assert MatchResult.objects.filter(job=job).count() == 2


class TestDateBoundaryMatching:
    """Freezegun tests that verify exact date-window boundary behaviour."""

    @freeze_time("2024-06-15")
    def test_fuzzy_match_at_exact_boundary(self) -> None:
        """A GL entry exactly DATE_WINDOW_DAYS away should still be a candidate."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 6, 15),
            reference="",
            description="Amazon Web Services Monthly",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 6, 15) + timedelta(days=DATE_WINDOW_DAYS),
            reference="DIFFERENT",
            description="Amazon Web Services Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 1

    @freeze_time("2024-06-15")
    def test_no_fuzzy_match_one_day_past_boundary(self) -> None:
        """A GL entry DATE_WINDOW_DAYS + 1 away should NOT be a candidate."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 6, 15),
            reference="",
            description="Amazon Web Services Monthly",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("100.00"),
            date=date(2024, 6, 15) + timedelta(days=DATE_WINDOW_DAYS + 1),
            reference="DIFFERENT",
            description="Amazon Web Services Payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 0

    @freeze_time("2024-01-01")
    def test_year_boundary_matching(self) -> None:
        """Matching should work correctly across year boundaries."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("500.00"),
            date=date(2023, 12, 30),
            reference="",
            description="Year-end office supplies purchase",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("500.00"),
            date=date(2024, 1, 2),  # 3 days later, across year boundary
            reference="DIFFERENT",
            description="Year-end office supplies payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 1

    @freeze_time("2024-02-28")
    def test_leap_year_boundary_matching(self) -> None:
        """Matching should work correctly around leap year dates."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=Decimal("250.00"),
            date=date(2024, 2, 28),
            reference="",
            description="Monthly subscription renewal",
        )
        GLEntryFactory(
            job=job,
            amount=Decimal("250.00"),
            date=date(2024, 3, 2),  # 3 days, crossing leap day
            reference="DIFFERENT",
            description="Monthly subscription payment",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["fuzzy_matches"] == 1
