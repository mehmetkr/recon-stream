"""Enable pg_trgm extension for trigram-based fuzzy matching."""

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        TrigramExtension(),
    ]
