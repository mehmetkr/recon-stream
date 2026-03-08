"""Django Ninja API endpoints for bank reconciliation."""

from typing import Any
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import File, Router
from ninja.files import UploadedFile

from reconciliation.models import MatchResult, ReconciliationJob
from reconciliation.schemas import (
    JobResponse,
    MatchResultOut,
    PaginatedMatchResults,
    StatsResponse,
    UploadResponse,
)
from reconciliation.services.ingestion import (
    IngestionError,
    ingest_bank_transactions,
    ingest_gl_entries,
)
from reconciliation.tasks import run_reconciliation

router = Router()


@router.post("/upload/bank-transactions/", response={201: UploadResponse, 422: dict})
def upload_bank_transactions(request: HttpRequest, file: File[UploadedFile]) -> tuple[int, UploadResponse | dict[str, Any]]:
    """Upload a CSV of bank transactions. Creates a new reconciliation job."""
    job = ReconciliationJob.objects.create()
    try:
        count = ingest_bank_transactions(job, file)
    except IngestionError as e:
        job.delete()
        return 422, {"detail": "Validation failed", "errors": e.errors}
    return 201, UploadResponse(job_id=job.id, rows_ingested=count)


@router.post("/upload/gl-entries/{job_id}/", response={201: UploadResponse, 404: dict, 422: dict})
def upload_gl_entries(request: HttpRequest, job_id: UUID, file: File[UploadedFile]) -> tuple[int, UploadResponse | dict[str, Any]]:
    """Upload a CSV of GL entries for an existing reconciliation job."""
    job = get_object_or_404(ReconciliationJob, id=job_id)
    try:
        count = ingest_gl_entries(job, file)
    except IngestionError as e:
        return 422, {"detail": "Validation failed", "errors": e.errors}
    return 201, UploadResponse(job_id=job.id, rows_ingested=count)


@router.post("/reconcile/{job_id}/", response={200: JobResponse, 202: JobResponse, 404: dict})
def reconcile(request: HttpRequest, job_id: UUID) -> tuple[int, JobResponse]:
    """Trigger async reconciliation matching for a job.

    Returns 200 if already completed, 202 if dispatched to worker.
    Uses transaction.on_commit to ensure the task is dispatched only
    after the current transaction commits.
    """
    from django.db import transaction

    job = get_object_or_404(ReconciliationJob, id=job_id)

    if job.status == ReconciliationJob.Status.COMPLETED:
        return 200, JobResponse(
            id=job.id, status=job.status, created_at=job.created_at, stats=job.stats
        )

    if job.status != ReconciliationJob.Status.PROCESSING:
        job.status = ReconciliationJob.Status.PENDING
        job.save(update_fields=["status", "updated_at"])

    # Dispatch async task after transaction commits
    transaction.on_commit(lambda: run_reconciliation.delay(str(job.id)))  # type: ignore[attr-defined]

    return 202, JobResponse(
        id=job.id, status=job.status, created_at=job.created_at, stats=job.stats
    )


@router.get("/results/{job_id}/", response=PaginatedMatchResults)
def get_results(request: HttpRequest, job_id: UUID, offset: int = 0, limit: int = 100) -> PaginatedMatchResults:
    """Get paginated match results for a job."""
    job = get_object_or_404(ReconciliationJob, id=job_id)

    matches = (
        MatchResult.objects.filter(job=job)
        .select_related("bank_transaction", "gl_entry")
        .order_by("-confidence")
    )

    count = matches.count()
    results = [
        MatchResultOut(
            id=m.id,
            match_type=m.match_type,
            confidence=m.confidence,
            matched_on=m.matched_on,
            bank_transaction_id=m.bank_transaction.id,
            bank_transaction_external_id=m.bank_transaction.external_id,
            bank_transaction_amount=m.bank_transaction.amount,
            bank_transaction_description=m.bank_transaction.description,
            gl_entry_id=m.gl_entry.id,
            gl_entry_gl_code=m.gl_entry.gl_code,
            gl_entry_amount=m.gl_entry.amount,
            gl_entry_description=m.gl_entry.description,
        )
        for m in matches[offset : offset + limit]
    ]

    return PaginatedMatchResults(count=count, results=results)


@router.get("/stats/{job_id}/", response={200: StatsResponse, 404: dict})
def get_stats(request: HttpRequest, job_id: UUID) -> tuple[int, StatsResponse]:
    """Get aggregated statistics for a reconciliation job."""
    job = get_object_or_404(ReconciliationJob, id=job_id)

    total_bank = job.bank_transactions.count()
    total_gl = job.gl_entries.count()
    exact = job.matches.filter(match_type=MatchResult.MatchType.EXACT).count()
    fuzzy = job.matches.filter(match_type=MatchResult.MatchType.FUZZY).count()

    return 200, StatsResponse(
        job_id=job.id,
        status=job.status,
        total_bank_transactions=total_bank,
        total_gl_entries=total_gl,
        exact_matches=exact,
        fuzzy_matches=fuzzy,
        unmatched_bank_transactions=total_bank - exact - fuzzy,
        unmatched_gl_entries=total_gl - exact - fuzzy,
        duration_ms=job.stats.get("duration_ms"),
    )
