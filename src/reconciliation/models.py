"""Domain models for bank reconciliation."""

from django.contrib.postgres.indexes import GinIndex
from django.db import models

from core.models import TimeStampedModel
from reconciliation.managers import UnmatchedBankTransactionQuerySet, UnmatchedGLEntryQuerySet


class ReconciliationJob(TimeStampedModel):  # type: ignore[django-manager-missing]
    """A single reconciliation run. Groups bank transactions and GL entries."""

    class Status(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    stats = models.JSONField(default=dict)  # {exact_matches, fuzzy_matches, unmatched, duration_ms}

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Job {self.id} [{self.status}]"


class BankTransaction(TimeStampedModel):
    """External bank feed record — treated as immutable after ingestion."""

    objects = UnmatchedBankTransactionQuerySet.as_manager()  # type: ignore[django-manager-missing]

    job = models.ForeignKey(ReconciliationJob, on_delete=models.CASCADE, related_name="bank_transactions")
    external_id = models.CharField(max_length=100)
    date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, db_index=True)
    description = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "external_id"], name="unique_bank_tx_per_job"),
        ]
        indexes = [
            GinIndex(name="bank_tx_desc_trgm", fields=["description"], opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return f"BankTx {self.external_id}: {self.amount}"


class GLEntry(TimeStampedModel):
    """Internal general ledger entry."""

    objects = UnmatchedGLEntryQuerySet.as_manager()  # type: ignore[django-manager-missing]

    job = models.ForeignKey(ReconciliationJob, on_delete=models.CASCADE, related_name="gl_entries")
    gl_code = models.CharField(max_length=50)
    date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, db_index=True)
    description = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        indexes = [
            GinIndex(name="gl_entry_desc_trgm", fields=["description"], opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return f"GL {self.gl_code}: {self.amount}"


class MatchResult(TimeStampedModel):
    """Records a match between a BankTransaction and a GLEntry."""

    class MatchType(models.TextChoices):
        EXACT = "EXACT"
        FUZZY = "FUZZY"

    job = models.ForeignKey(ReconciliationJob, on_delete=models.CASCADE, related_name="matches")
    bank_transaction = models.OneToOneField(BankTransaction, on_delete=models.CASCADE)
    gl_entry = models.OneToOneField(GLEntry, on_delete=models.CASCADE)
    match_type = models.CharField(max_length=10, choices=MatchType.choices)
    confidence = models.DecimalField(max_digits=5, decimal_places=4)  # 0.0000–1.0000
    matched_on = models.JSONField(default=list)  # ["amount", "date", "description"] — audit trail

    def __str__(self) -> str:
        return f"Match [{self.match_type}] conf={self.confidence}"
