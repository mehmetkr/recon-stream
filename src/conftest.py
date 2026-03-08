"""Root conftest for pytest-django."""

import pytest


@pytest.fixture(autouse=True)
def _enable_db_access_for_all_tests(db: None) -> None:
    """Automatically grant DB access to all tests."""
