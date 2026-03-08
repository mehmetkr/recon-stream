"""CSV ingestion service for bank transactions and GL entries."""

import csv
import io
from collections.abc import Iterator

import structlog
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from pydantic import ValidationError

from reconciliation.models import BankTransaction, GLEntry, ReconciliationJob
from reconciliation.schemas import BankTransactionIn, GLEntryIn

log = structlog.get_logger("reconciliation.ingestion")

BATCH_SIZE = 1000


class IngestionError(Exception):
    """Raised when CSV ingestion fails validation."""

    def __init__(self, errors: list[dict]) -> None:  # type: ignore[type-arg]
        self.errors = errors
        super().__init__(f"Ingestion failed with {len(errors)} errors")


def _read_csv_rows(file: UploadedFile) -> Iterator[dict[str, str]]:
    """Generator that yields CSV rows as dicts without loading full file into RAM."""
    content = file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    yield from reader


def ingest_bank_transactions(job: ReconciliationJob, file: UploadedFile) -> int:
    """Parse and ingest bank transactions from CSV.

    Returns the number of rows ingested.
    Raises IngestionError if any row fails validation.
    """
    rows = list(_read_csv_rows(file))
    if not rows:
        return 0

    # Validate all rows first — fail fast
    validated: list[BankTransactionIn] = []
    errors: list[dict] = []  # type: ignore[type-arg]
    for i, row in enumerate(rows):
        try:
            validated.append(BankTransactionIn(**row))  # type: ignore[arg-type]
        except ValidationError as e:
            errors.append({"row": i + 1, "errors": e.errors()})

    if errors:
        raise IngestionError(errors)

    # Bulk create in batches inside a single transaction
    with transaction.atomic():
        instances = [
            BankTransaction(
                job=job,
                external_id=v.external_id,
                date=v.date,
                amount=v.amount,
                description=v.description,
                reference=v.reference,
            )
            for v in validated
        ]
        for i in range(0, len(instances), BATCH_SIZE):
            BankTransaction.objects.bulk_create(instances[i : i + BATCH_SIZE])

    log.info("bank_transactions_ingested", job_id=str(job.id), row_count=len(validated))
    return len(validated)


def ingest_gl_entries(job: ReconciliationJob, file: UploadedFile) -> int:
    """Parse and ingest GL entries from CSV.

    Returns the number of rows ingested.
    Raises IngestionError if any row fails validation.
    """
    rows = list(_read_csv_rows(file))
    if not rows:
        return 0

    validated: list[GLEntryIn] = []
    errors: list[dict] = []  # type: ignore[type-arg]
    for i, row in enumerate(rows):
        try:
            validated.append(GLEntryIn(**row))  # type: ignore[arg-type]
        except ValidationError as e:
            errors.append({"row": i + 1, "errors": e.errors()})

    if errors:
        raise IngestionError(errors)

    with transaction.atomic():
        instances = [
            GLEntry(
                job=job,
                gl_code=v.gl_code,
                date=v.date,
                amount=v.amount,
                description=v.description,
                reference=v.reference,
            )
            for v in validated
        ]
        for i in range(0, len(instances), BATCH_SIZE):
            GLEntry.objects.bulk_create(instances[i : i + BATCH_SIZE])

    log.info("gl_entries_ingested", job_id=str(job.id), row_count=len(validated))
    return len(validated)
