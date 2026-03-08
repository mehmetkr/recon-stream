"""Generate seed data for ReconStream benchmarks.

Usage: python src/scripts/seed_data.py [--count 10000]
"""

import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
django.setup()

from reconciliation.models import BankTransaction, GLEntry, ReconciliationJob  # noqa: E402

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
    "Shopify Commerce",
    "Atlassian Jira",
    "GitHub Enterprise",
    "PagerDuty Alerts",
    "Notion Workspace",
]

# Slight description variations for fuzzy matching scenarios
FUZZY_VARIANTS = {
    "Starbucks Coffee": ["Starbucks Cfe", "STARBUCKS COFFEE CO", "Starbux Coffee"],
    "Amazon Web Services": ["AWS", "Amazon AWS", "AMZN Web Svcs"],
    "Uber Technologies": ["Uber *Pending", "UBER TECH", "Uber Ride"],
    "Google Cloud Platform": ["GCP", "Google Cloud", "GOOGLE CLOUD PLAT"],
    "Microsoft Azure": ["MSFT Azure", "Microsoft Az", "MS Azure Cloud"],
}

GL_CODES = ["6100", "6200", "6300", "6400", "6500", "6600", "6700", "6800"]

BATCH_SIZE = 1000


def generate_seed_data(count: int = 10000) -> None:
    """Generate seed data with a mix of exact, fuzzy, and unmatched records."""
    print(f"Generating {count} transaction pairs...")

    job = ReconciliationJob.objects.create(status=ReconciliationJob.Status.PENDING)

    bank_txs: list[BankTransaction] = []
    gl_entries: list[GLEntry] = []

    base_date = date.today() - timedelta(days=60)

    for i in range(count):
        tx_date = base_date + timedelta(days=random.randint(0, 60))
        amount = Decimal(f"{random.uniform(10.0, 50000.0):.2f}")
        merchant = random.choice(MERCHANT_NAMES)
        ref = f"REF-{i:06d}"

        # Decide match type: 60% exact, 25% fuzzy, 15% unmatched
        roll = random.random()

        bank_desc = f"{merchant} #{random.randint(100, 999)}"
        bank_txs.append(
            BankTransaction(
                job=job,
                external_id=f"BANK-{i:08d}",
                date=tx_date,
                amount=amount,
                description=bank_desc,
                reference=ref,
            )
        )

        if roll < 0.60:
            # Exact match: same amount, date, reference
            gl_entries.append(
                GLEntry(
                    job=job,
                    gl_code=random.choice(GL_CODES),
                    date=tx_date,
                    amount=amount,
                    description=f"{merchant} Payment",
                    reference=ref,
                )
            )
        elif roll < 0.85:
            # Fuzzy match: slight variations
            date_offset = random.randint(-3, 3)
            amount_offset = Decimal(f"{random.uniform(-0.08, 0.08):.2f}")
            fuzzy_desc = random.choice(FUZZY_VARIANTS.get(merchant, [f"{merchant} Pmt"]))
            gl_entries.append(
                GLEntry(
                    job=job,
                    gl_code=random.choice(GL_CODES),
                    date=tx_date + timedelta(days=date_offset),
                    amount=amount + amount_offset,
                    description=fuzzy_desc,
                    reference="",  # No reference for fuzzy
                )
            )
        else:
            # Unmatched: GL entry with completely different data
            gl_entries.append(
                GLEntry(
                    job=job,
                    gl_code=random.choice(GL_CODES),
                    date=base_date + timedelta(days=random.randint(0, 60)),
                    amount=Decimal(f"{random.uniform(10.0, 50000.0):.2f}"),
                    description=f"{random.choice(MERCHANT_NAMES)} Internal Transfer",
                    reference=f"INT-{random.randint(100000, 999999)}",
                )
            )

        # Bulk create in batches
        if len(bank_txs) >= BATCH_SIZE:
            BankTransaction.objects.bulk_create(bank_txs)
            GLEntry.objects.bulk_create(gl_entries)
            print(f"  Created {i + 1} pairs...")
            bank_txs = []
            gl_entries = []

    # Final batch
    if bank_txs:
        BankTransaction.objects.bulk_create(bank_txs)
        GLEntry.objects.bulk_create(gl_entries)

    print(f"Done. Job ID: {job.id}")
    print(f"  Bank transactions: {job.bank_transactions.count()}")
    print(f"  GL entries: {job.gl_entries.count()}")


if __name__ == "__main__":
    count = 10000
    if len(sys.argv) > 1 and sys.argv[1] == "--count":
        count = int(sys.argv[2])
    generate_seed_data(count)
