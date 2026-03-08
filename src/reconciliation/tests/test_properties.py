"""Property-based tests using Hypothesis for reconciliation invariants.

These tests verify system-level properties that must hold regardless of input,
rather than testing specific example cases.
"""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from reconciliation.models import BankTransaction, GLEntry, MatchResult
from reconciliation.services.matcher import ReconciliationMatcher
from reconciliation.tests.factories import (
    BankTransactionFactory,
    GLEntryFactory,
    ReconciliationJobFactory,
)

# --- Strategies ---

reasonable_amount = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("99999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

reasonable_date = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2030, 12, 31),
)

reasonable_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    min_size=5,
    max_size=100,
)


@pytest.mark.django_db(transaction=True)
class TestMatchingInvariants:
    """Property-based tests for matching engine invariants."""

    @given(amount=reasonable_amount, txn_date=reasonable_date, ref=reasonable_text)
    @settings(max_examples=20, deadline=10000)
    def test_exact_same_data_always_matches(
        self, amount: Decimal, txn_date: date, ref: str
    ) -> None:
        """If bank tx and GL entry share amount, date, and reference, they must match."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=amount,
            date=txn_date,
            reference=ref,
            description="Property test bank",
        )
        GLEntryFactory(
            job=job,
            amount=amount,
            date=txn_date,
            reference=ref,
            description="Property test GL",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        assert stats["exact_matches"] == 1
        assert stats["fuzzy_matches"] == 0

    @given(
        amount_a=reasonable_amount,
        amount_b=reasonable_amount,
        txn_date=reasonable_date,
    )
    @settings(max_examples=20, deadline=10000)
    def test_match_count_never_exceeds_min_of_sides(
        self, amount_a: Decimal, amount_b: Decimal, txn_date: date
    ) -> None:
        """Total matches can never exceed min(bank_tx_count, gl_entry_count)."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=amount_a,
            date=txn_date,
            reference="R1",
            description="Bank A",
        )
        BankTransactionFactory(
            job=job,
            amount=amount_b,
            date=txn_date,
            reference="R2",
            description="Bank B",
        )
        GLEntryFactory(
            job=job,
            amount=amount_a,
            date=txn_date,
            reference="R1",
            description="GL A",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        total_matches = stats["exact_matches"] + stats["fuzzy_matches"]
        bank_count = BankTransaction.objects.filter(job=job).count()
        gl_count = GLEntry.objects.filter(job=job).count()

        assert total_matches <= min(bank_count, gl_count)

    @given(amount=reasonable_amount, txn_date=reasonable_date)
    @settings(max_examples=15, deadline=10000)
    def test_no_double_matching(self, amount: Decimal, txn_date: date) -> None:
        """A GL entry should never be matched to more than one bank transaction."""
        job = ReconciliationJobFactory()

        # Two bank txs that both could match the same GL entry
        BankTransactionFactory(
            job=job,
            amount=amount,
            date=txn_date,
            reference="SHARED",
            description="Bank tx one",
        )
        BankTransactionFactory(
            job=job,
            amount=amount,
            date=txn_date,
            reference="SHARED",
            description="Bank tx two",
        )
        GLEntryFactory(
            job=job,
            amount=amount,
            date=txn_date,
            reference="SHARED",
            description="GL entry",
        )

        matcher = ReconciliationMatcher(job)
        matcher.run()

        # OneToOneField on gl_entry enforces this at DB level, but verify in stats
        matches = MatchResult.objects.filter(job=job)
        gl_ids = list(matches.values_list("gl_entry_id", flat=True))
        assert len(gl_ids) == len(set(gl_ids)), "GL entry matched to multiple bank txs"

    @given(
        bank_amount=reasonable_amount,
        txn_date=reasonable_date,
    )
    @settings(max_examples=15, deadline=10000)
    def test_unmatched_counts_consistent(
        self, bank_amount: Decimal, txn_date: date
    ) -> None:
        """unmatched_bank + exact + fuzzy == total bank transactions."""
        job = ReconciliationJobFactory()
        BankTransactionFactory(
            job=job,
            amount=bank_amount,
            date=txn_date,
            reference="REF-1",
            description="Bank only",
        )

        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        total_bank = BankTransaction.objects.filter(job=job).count()
        matched = stats["exact_matches"] + stats["fuzzy_matches"]

        assert stats["unmatched_bank_transactions"] == total_bank - matched
