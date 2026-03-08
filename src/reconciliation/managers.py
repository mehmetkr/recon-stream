"""Custom QuerySet managers for reconciliation models."""

from django.db import models


class UnmatchedBankTransactionQuerySet(models.QuerySet):  # type: ignore[type-arg]
    """QuerySet that filters to bank transactions without a match."""

    def unmatched(self) -> "UnmatchedBankTransactionQuerySet":
        return self.filter(matchresult__isnull=True)


class UnmatchedGLEntryQuerySet(models.QuerySet):  # type: ignore[type-arg]
    """QuerySet that filters to GL entries without a match."""

    def unmatched(self) -> "UnmatchedGLEntryQuerySet":
        return self.filter(matchresult__isnull=True)
