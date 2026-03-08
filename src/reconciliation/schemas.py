"""Pydantic schemas for reconciliation API request/response DTOs."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import condecimal


class BankTransactionIn(Schema):
    """Schema for a single bank transaction row from CSV."""

    external_id: str
    date: date
    amount: condecimal(max_digits=14, decimal_places=2)  # type: ignore[valid-type]
    description: str
    reference: str = ""


class GLEntryIn(Schema):
    """Schema for a single GL entry row from CSV."""

    gl_code: str
    date: date
    amount: condecimal(max_digits=14, decimal_places=2)  # type: ignore[valid-type]
    description: str
    reference: str = ""


class JobResponse(Schema):
    """Response schema for a reconciliation job."""

    id: UUID
    status: str
    created_at: datetime
    stats: dict  # type: ignore[type-arg]


class UploadResponse(Schema):
    """Response after CSV upload."""

    job_id: UUID
    rows_ingested: int


class MatchResultOut(Schema):
    """Response schema for a single match result."""

    id: UUID
    match_type: str
    confidence: Decimal
    matched_on: list[str]
    bank_transaction_id: UUID
    bank_transaction_external_id: str
    bank_transaction_amount: Decimal
    bank_transaction_description: str
    gl_entry_id: UUID
    gl_entry_gl_code: str
    gl_entry_amount: Decimal
    gl_entry_description: str


class PaginatedMatchResults(Schema):
    """Paginated response for match results."""

    count: int
    results: list[MatchResultOut]


class StatsResponse(Schema):
    """Aggregated job statistics."""

    job_id: UUID
    status: str
    total_bank_transactions: int
    total_gl_entries: int
    exact_matches: int
    fuzzy_matches: int
    unmatched_bank_transactions: int
    unmatched_gl_entries: int
    duration_ms: int | None = None
