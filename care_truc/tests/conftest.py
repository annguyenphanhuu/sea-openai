"""Shared deterministic fixtures for isolated A1 tests."""
from datetime import datetime, timezone
import pytest
from care_truc.models import Principal, TrustedContext


@pytest.fixture
def trusted_context():
    return TrustedContext(Principal('customer-1', False), 'test-run',
                          datetime(2026, 10, 31, tzinfo=timezone.utc))
