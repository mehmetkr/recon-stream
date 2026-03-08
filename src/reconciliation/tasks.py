"""Celery tasks for reconciliation processing."""

import structlog
from celery import shared_task
from django.utils import timezone

from reconciliation.models import ReconciliationJob
from reconciliation.services.matcher import ReconciliationMatcher

log = structlog.get_logger("reconciliation.tasks")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def run_reconciliation(self, job_id: str) -> dict:  # type: ignore[type-arg, no-untyped-def]
    """Run the reconciliation matching engine for a job.

    Idempotent: checks job status first, skips if already completed.
    Resilient: retries on failure with exponential backoff.
    """
    task_log = log.bind(job_id=job_id, celery_task_id=self.request.id)
    task_log.info("task_received")

    job = ReconciliationJob.objects.get(id=job_id)

    # Idempotent — skip if already completed
    if job.status == ReconciliationJob.Status.COMPLETED:
        task_log.info("task_skipped_already_completed")
        return job.stats  # type: ignore[no-any-return]

    job.status = ReconciliationJob.Status.PROCESSING
    job.save(update_fields=["status", "updated_at"])

    try:
        matcher = ReconciliationMatcher(job)
        stats = matcher.run()

        job.status = ReconciliationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "updated_at"])

        task_log.info("task_completed", **stats)
        return stats

    except Exception as exc:
        job.status = ReconciliationJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=["status", "error_message", "updated_at"])
        task_log.error("task_failed", error=str(exc), retry=self.request.retries)
        raise self.retry(exc=exc) from exc
