"""Smoke tests to verify factories create valid model instances."""

from reconciliation.tests.factories import (
    BankTransactionFactory,
    GLEntryFactory,
    MatchResultFactory,
    ReconciliationJobFactory,
)


def test_create_reconciliation_job() -> None:
    job = ReconciliationJobFactory()
    assert job.pk is not None
    assert job.status == "PENDING"


def test_create_bank_transaction() -> None:
    tx = BankTransactionFactory()
    assert tx.pk is not None
    assert tx.job is not None
    assert tx.amount > 0


def test_create_gl_entry() -> None:
    entry = GLEntryFactory()
    assert entry.pk is not None
    assert entry.job is not None
    assert entry.gl_code != ""


def test_create_match_result() -> None:
    match = MatchResultFactory()
    assert match.pk is not None
    assert match.bank_transaction.job == match.job
    assert match.gl_entry.job == match.job
    assert match.confidence > 0
