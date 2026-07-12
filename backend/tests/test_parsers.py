from datetime import UTC

from quakerelay.models import EventStatus
from quakerelay.parsers import parse_payload


def test_parse_cenc_eew_magnitude_spelling() -> None:
    reports = parse_payload(
        {
            "type": "cenc_eew",
            "ID": "123",
            "EventID": "202607120001",
            "ReportTime": "2026-07-12 12:00:02",
            "ReportNum": 2,
            "OriginTime": "2026-07-12 12:00:00",
            "HypoCenter": "四川某地",
            "Latitude": 30.1,
            "Longitude": 103.2,
            "Magnitude": 4.6,
            "Depth": None,
            "MaxIntensity": 5,
        }
    )
    assert len(reports) == 1
    report = reports[0]
    assert report.magnitude == 4.6
    assert report.depth_km is None
    assert report.origin_time.tzinfo == UTC
    assert report.report_number == 2


def test_parse_provincial_magunitude_and_final() -> None:
    report = parse_payload(
        {
            "type": "fj_eew",
            "ID": 55,
            "EventID": "event-55",
            "ReportTime": "2026-07-12 12:00:02",
            "ReportNum": 3,
            "OriginTime": "2026-07-12 12:00:00",
            "HypoCenter": "福建某地",
            "Latitude": 25.1,
            "Longitude": 118.2,
            "Magunitude": "3.8",
            "isFinal": True,
        }
    )[0]
    assert report.magnitude == 3.8
    assert report.status == EventStatus.final


def test_parse_cenc_list_snapshot() -> None:
    reports = parse_payload(
        {
            "type": "cenc_eqlist",
            "No1": {
                "type": "reviewed",
                "time": "2026-07-12 12:00:00",
                "location": "云南某地",
                "magnitude": "5.1",
                "depth": "10",
                "latitude": "25.0",
                "longitude": "101.0",
                "intensity": "6",
                "md5": "abc",
            },
        }
    )
    assert len(reports) == 1
    assert reports[0].status == EventStatus.reviewed
    assert reports[0].source_event_id == "abc"


def test_unsupported_source_is_ignored() -> None:
    assert parse_payload({"type": "jma_eew"}) == []
