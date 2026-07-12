import hashlib
from datetime import UTC, datetime

from quakerelay.fusion import FusionService
from quakerelay.models import (
    Earthquake,
    EventRevision,
    ImpactEstimate,
    Location,
    NotificationJob,
    RawMessage,
    SourceReport,
    WebhookEndpoint,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _raw(session: Session, payload: dict[str, object], digest: str) -> RawMessage:
    raw = RawMessage(source=str(payload["type"]), content_hash=digest, payload=payload)
    session.add(raw)
    session.flush()
    return raw


def _payload(
    source: str, event_id: str, magnitude: float, report_number: int = 1
) -> dict[str, object]:
    return {
        "type": source,
        "ID": event_id,
        "EventID": event_id,
        "ReportTime": "2026-07-12 12:00:02",
        "ReportNum": report_number,
        "OriginTime": "2026-07-12 12:00:00",
        "HypoCenter": "测试震中",
        "Latitude": 30.0,
        "Longitude": 110.0,
        "Magnitude": magnitude,
        "Depth": 10,
    }


def test_multi_source_merge_revisions_and_impact(session: Session) -> None:
    # Keep fixture dates fresh enough for notification generation.
    now = datetime.now(UTC).astimezone().replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    session.add(Location(name="家", latitude=30.05, longitude=110.05))
    session.flush()

    first = _payload("sc_eew", "sc-1", 4.5)
    first["ReportTime"] = first["OriginTime"] = now
    FusionService().process_raw(session, _raw(session, first, hashlib.sha256(b"1").hexdigest()))
    session.flush()

    second = _payload("cenc_eew", "cenc-1", 4.9)
    second["ReportTime"] = second["OriginTime"] = now
    FusionService().process_raw(session, _raw(session, second, hashlib.sha256(b"2").hexdigest()))
    session.commit()

    assert session.scalar(select(func.count(Earthquake.id))) == 1
    event = session.scalar(select(Earthquake))
    assert event is not None
    assert event.magnitude == 4.9
    assert event.revision == 2
    assert session.scalar(select(func.count(SourceReport.id))) == 2
    assert session.scalar(select(func.count(EventRevision.id))) == 2
    assert session.scalar(select(func.count(ImpactEstimate.id))) == 2


def test_notification_is_merged_for_all_locations(session: Session) -> None:
    session.add_all(
        [
            Location(name="地点A", latitude=30.05, longitude=110.05),
            Location(name="地点B", latitude=30.1, longitude=110.1),
            WebhookEndpoint(name="test", url="https://example.com", encrypted_headers=b""),
        ]
    )
    payload = _payload("cenc_eew", "event-now", 5.0)
    now = datetime.now(UTC).astimezone().replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    payload["ReportTime"] = payload["OriginTime"] = now
    FusionService().process_raw(session, _raw(session, payload, "3" * 64))
    session.commit()
    job = session.scalar(select(NotificationJob))
    assert job is not None
    assert len(job.payload["impacts"]) == 2
    assert job.kind == "earthquake.initial"


def test_corrected_same_report_number_is_preserved(session: Session) -> None:
    first = _payload("cenc_eew", "corrected", 4.0, report_number=1)
    second = _payload("cenc_eew", "corrected", 4.5, report_number=1)
    now = datetime.now(UTC).astimezone().replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    first["ReportTime"] = first["OriginTime"] = now
    second["ReportTime"] = second["OriginTime"] = now
    service = FusionService()
    service.process_raw(session, _raw(session, first, "4" * 64))
    service.process_raw(session, _raw(session, second, "5" * 64))
    session.commit()

    reports = session.scalars(select(SourceReport)).all()
    event = session.scalar(select(Earthquake))
    assert len(reports) == 2
    assert event is not None
    assert event.magnitude == 4.5
    assert event.revision == 2
