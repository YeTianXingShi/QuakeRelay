from datetime import UTC, datetime

from quakerelay.api import _utc
from quakerelay.notifications import _utc_iso


def test_naive_database_datetime_is_serialized_as_utc() -> None:
    value = datetime(2026, 7, 12, 7, 41, 8)
    normalized = _utc(value)
    assert normalized is not None
    assert normalized.tzinfo == UTC
    assert _utc_iso(value) == "2026-07-12T07:41:08+00:00"
