from datetime import UTC, datetime, timedelta

from quakerelay.models import Location, NotificationJob, WeatherSnapshot, WebhookEndpoint
from quakerelay.notifications import enqueue_weather_notification
from quakerelay.weather import (
    ingest_weather_payload,
    latest_is_notifiable,
    location_matches_station,
    normalize_admin_name,
    weather_matches,
)
from sqlalchemy import select


def _payload(value: str = "40.0 ℃") -> dict:
    return {
        "202607121700": {
            "tempRank": [{"province": "福建", "city": "宁德福鼎市", "value": value}],
            "rainRank": [],
            "windSRank": [],
        },
        "202607121600": {
            "tempRank": [],
            "rainRank": [{"province": "四川", "city": "高县", "value": "20.0 mm"}],
            "windSRank": [],
        },
        "md5": "ignored",
    }


def test_normalizes_administrative_names_and_matches_station() -> None:
    assert normalize_admin_name("福建省") == "福建"
    assert normalize_admin_name("新疆维吾尔自治区") == "新疆"
    location = Location(
        name="家",
        address="福建省宁德市福鼎市",
        province="福建省",
        city="宁德市",
        district="福鼎市",
        latitude=27.3,
        longitude=120.2,
    )
    assert location_matches_station(location, "福建", "宁德福鼎市")
    assert not location_matches_station(location, "浙江", "福鼎")


def test_ingests_all_hours_and_updates_changed_hour(session) -> None:
    snapshots, latest = ingest_weather_payload(session, _payload())
    session.flush()
    assert len(snapshots) == 2
    assert latest is not None and latest.hour_key == "202607121700"
    ingest_weather_payload(session, _payload("41.0 ℃"))
    session.flush()
    rows = session.scalars(select(WeatherSnapshot)).all()
    assert len(rows) == 2
    current = next(row for row in rows if row.hour_key == "202607121700")
    assert current.temperature_rank[0]["value"] == "41.0 ℃"


def test_matches_enabled_structured_locations(session) -> None:
    session.add(
        Location(
            name="家",
            address="福建省宁德市福鼎市",
            province="福建省",
            city="宁德市",
            district="福鼎市",
            latitude=27.3,
            longitude=120.2,
        )
    )
    _, snapshot = ingest_weather_payload(session, _payload())
    session.flush()
    assert snapshot is not None
    matches = weather_matches(session, snapshot)
    assert len(matches) == 1
    assert matches[0]["location_names"] == ["家"]


def test_only_recent_latest_snapshot_is_notifiable() -> None:
    snapshot = WeatherSnapshot(
        hour_key="202607121700",
        observed_at=datetime(2026, 7, 12, 9, 0, tzinfo=UTC),
        content_hash="x",
    )
    assert latest_is_notifiable(snapshot, datetime(2026, 7, 12, 10, 59, tzinfo=UTC))
    assert not latest_is_notifiable(snapshot, datetime(2026, 7, 12, 11, 1, tzinfo=UTC))
    assert not latest_is_notifiable(snapshot, snapshot.observed_at - timedelta(minutes=1))


def test_weather_notifications_only_use_subscribed_channels(session) -> None:
    weather_endpoint = WebhookEndpoint(
        name="气象",
        url="https://example.com/weather",
        enabled=True,
        earthquake_enabled=False,
        weather_enabled=True,
    )
    earthquake_endpoint = WebhookEndpoint(
        name="地震",
        url="https://example.com/earthquake",
        enabled=True,
        earthquake_enabled=True,
        weather_enabled=False,
    )
    session.add_all([weather_endpoint, earthquake_endpoint])
    _, snapshot = ingest_weather_payload(session, _payload())
    session.flush()
    assert snapshot is not None
    count = enqueue_weather_notification(
        session,
        snapshot,
        [{"kind": "temperature", "rank": 1, "location_names": ["家"]}],
    )
    session.flush()
    jobs = session.scalars(select(NotificationJob)).all()
    assert count == 1
    assert len(jobs) == 1
    assert jobs[0].endpoint_id == weather_endpoint.id
