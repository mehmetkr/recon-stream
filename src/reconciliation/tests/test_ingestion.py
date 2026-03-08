"""Tests for the CSV ingestion service."""


import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from reconciliation.models import BankTransaction, GLEntry
from reconciliation.services.ingestion import (
    IngestionError,
    ingest_bank_transactions,
    ingest_gl_entries,
)
from reconciliation.tests.factories import ReconciliationJobFactory


def _make_csv(header: str, rows: list[str]) -> SimpleUploadedFile:
    """Helper to create a SimpleUploadedFile from CSV content."""
    content = header + "\n" + "\n".join(rows) + "\n"
    return SimpleUploadedFile("test.csv", content.encode("utf-8"), content_type="text/csv")


class TestIngestBankTransactions:
    def test_valid_csv_creates_rows(self) -> None:
        job = ReconciliationJobFactory()
        csv_file = _make_csv(
            "external_id,date,amount,description,reference",
            [
                "TXN-001,2024-01-15,100.50,Starbucks Coffee #123,REF-001",
                "TXN-002,2024-01-16,250.00,Amazon Web Services,REF-002",
            ],
        )
        count = ingest_bank_transactions(job, csv_file)
        assert count == 2
        assert BankTransaction.objects.filter(job=job).count() == 2

    def test_empty_csv_returns_zero(self) -> None:
        job = ReconciliationJobFactory()
        csv_file = _make_csv("external_id,date,amount,description,reference", [])
        count = ingest_bank_transactions(job, csv_file)
        assert count == 0

    def test_invalid_amount_raises_ingestion_error(self) -> None:
        job = ReconciliationJobFactory()
        csv_file = _make_csv(
            "external_id,date,amount,description,reference",
            ["TXN-001,2024-01-15,not_a_number,Starbucks,REF-001"],
        )
        with pytest.raises(IngestionError) as exc_info:
            ingest_bank_transactions(job, csv_file)
        assert len(exc_info.value.errors) == 1
        assert exc_info.value.errors[0]["row"] == 1

    def test_invalid_date_raises_ingestion_error(self) -> None:
        job = ReconciliationJobFactory()
        csv_file = _make_csv(
            "external_id,date,amount,description,reference",
            ["TXN-001,not-a-date,100.50,Starbucks,REF-001"],
        )
        with pytest.raises(IngestionError):
            ingest_bank_transactions(job, csv_file)

    def test_rollback_on_validation_error(self) -> None:
        """If any row is invalid, no rows should be committed."""
        job = ReconciliationJobFactory()
        csv_file = _make_csv(
            "external_id,date,amount,description,reference",
            [
                "TXN-001,2024-01-15,100.50,Starbucks,REF-001",
                "TXN-002,bad-date,200.00,Amazon,REF-002",
            ],
        )
        with pytest.raises(IngestionError):
            ingest_bank_transactions(job, csv_file)
        assert BankTransaction.objects.filter(job=job).count() == 0


class TestIngestGLEntries:
    def test_valid_csv_creates_rows(self) -> None:
        job = ReconciliationJobFactory()
        csv_file = _make_csv(
            "gl_code,date,amount,description,reference",
            [
                "6100,2024-01-15,100.50,Office Supplies Payment,REF-001",
                "6200,2024-01-16,250.00,Software Subscription,REF-002",
            ],
        )
        count = ingest_gl_entries(job, csv_file)
        assert count == 2
        assert GLEntry.objects.filter(job=job).count() == 2

    def test_empty_csv_returns_zero(self) -> None:
        job = ReconciliationJobFactory()
        csv_file = _make_csv("gl_code,date,amount,description,reference", [])
        count = ingest_gl_entries(job, csv_file)
        assert count == 0
