from datetime import UTC, datetime

from app.services.business_hours import is_within_business_hours_config


def test_business_hours_converts_utc_across_previous_local_day() -> None:
    hours = {"sunday": [{"open": "18:00:00", "close": "23:00:00"}]}
    assert is_within_business_hours_config(
        datetime(2026, 9, 7, 1, 30, tzinfo=UTC), "America/New_York", hours
    )


def test_business_hours_handles_dst_zone_without_manual_offset() -> None:
    hours = {"sunday": [{"open": "01:00:00", "close": "04:00:00"}]}
    assert is_within_business_hours_config(
        datetime(2026, 3, 8, 7, 30, tzinfo=UTC), "America/New_York", hours
    )
