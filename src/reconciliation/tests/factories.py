"""Factory Boy factories for reconciliation models."""

import random
from datetime import date, timedelta
from decimal import Decimal

import factory

from reconciliation.models import (
    BankTransaction,
    GLEntry,
    MatchResult,
    ReconciliationJob,
)

# Realistic merchant/vendor descriptions for financial data
MERCHANT_NAMES = [
    "Starbucks Coffee",
    "Amazon Web Services",
    "Uber Technologies",
    "WeWork Office Space",
    "Slack Technologies",
    "Google Cloud Platform",
    "Microsoft Azure",
    "Stripe Payment Processing",
    "Gusto Payroll Services",
    "Adobe Creative Cloud",
    "Zoom Video Communications",
    "HubSpot Marketing",
    "Salesforce CRM",
    "Twilio Communications",
    "Datadog Monitoring",
]

GL_CODES = [
    "6100",  # Office Supplies
    "6200",  # Software & Subscriptions
    "6300",  # Cloud Infrastructure
    "6400",  # Travel & Entertainment
    "6500",  # Professional Services
    "6600",  # Marketing
    "6700",  # Payroll
    "6800",  # Rent & Utilities
]


class ReconciliationJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReconciliationJob

    status = ReconciliationJob.Status.PENDING


class BankTransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BankTransaction

    job = factory.SubFactory(ReconciliationJobFactory)
    external_id = factory.Sequence(lambda n: f"TXN-{n:06d}")
    date = factory.LazyFunction(lambda: date.today() - timedelta(days=random.randint(0, 30)))
    amount = factory.LazyFunction(lambda: Decimal(f"{random.uniform(10.0, 5000.0):.2f}"))
    description = factory.LazyFunction(lambda: f"{random.choice(MERCHANT_NAMES)} #{random.randint(100, 999)}")
    reference = factory.Sequence(lambda n: f"REF-{n:04d}")


class GLEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GLEntry

    job = factory.SubFactory(ReconciliationJobFactory)
    gl_code = factory.LazyFunction(lambda: random.choice(GL_CODES))
    date = factory.LazyFunction(lambda: date.today() - timedelta(days=random.randint(0, 30)))
    amount = factory.LazyFunction(lambda: Decimal(f"{random.uniform(10.0, 5000.0):.2f}"))
    description = factory.LazyFunction(lambda: f"{random.choice(MERCHANT_NAMES)} Payment")
    reference = factory.Sequence(lambda n: f"GLREF-{n:04d}")


class MatchResultFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MatchResult

    job = factory.SubFactory(ReconciliationJobFactory)
    bank_transaction = factory.SubFactory(BankTransactionFactory, job=factory.SelfAttribute("..job"))
    gl_entry = factory.SubFactory(GLEntryFactory, job=factory.SelfAttribute("..job"))
    match_type = MatchResult.MatchType.EXACT
    confidence = Decimal("1.0000")
    matched_on = factory.LazyFunction(lambda: ["amount", "date", "reference"])
