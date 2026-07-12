from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from .models import EventStatus

CST = timezone(timedelta(hours=8))
SUPPORTED_SOURCES = {"sc_eew", "fj_eew", "cq_eew", "cenc_eew", "cenc_eqlist"}


@dataclass(frozen=True)
class ParsedReport:
    source: str
    source_event_id: str
    report_number: int
    report_time: datetime
    origin_time: datetime
    hypocenter: str
    latitude: float
    longitude: float
    magnitude: float | None
    depth_km: float | None
    max_intensity: str | None
    status: EventStatus
    is_cancelled: bool


def _parse_time(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, UTC)
    text = str(value).strip().replace("/", "-")
    if text.endswith("Z") or "+" in text[10:]:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CST)
    return parsed.astimezone(UTC)


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).replace("km", "").replace("千米", "").strip()
    return float(text)


def _status(item: dict[str, Any]) -> EventStatus:
    if bool(item.get("isCancel") or item.get("is_cancelled")):
        return EventStatus.cancelled
    value = str(item.get("status") or item.get("type") or "").lower()
    if value in {"reviewed", "formal", "正式"}:
        return EventStatus.reviewed
    if bool(item.get("isFinal")):
        return EventStatus.final
    return EventStatus.preliminary


def _parse_eew(source: str, item: dict[str, Any]) -> ParsedReport:
    event_id = str(item.get("EventID") or item.get("ID") or "")
    report_time = _parse_time(item.get("ReportTime") or item.get("AnnouncedTime"))
    origin_time = _parse_time(item.get("OriginTime"))
    if not event_id:
        event_id = sha256(
            f"{source}:{origin_time.isoformat()}:{item.get('Latitude')}:{item.get('Longitude')}".encode()
        ).hexdigest()[:24]
    status = _status(item)
    return ParsedReport(
        source=source,
        source_event_id=event_id,
        report_number=int(item.get("ReportNum") or item.get("Serial") or 1),
        report_time=report_time,
        origin_time=origin_time,
        hypocenter=str(item.get("HypoCenter") or item.get("Hypocenter") or "未知震中"),
        latitude=float(item["Latitude"]),
        longitude=float(item["Longitude"]),
        magnitude=_float(item.get("Magnitude", item.get("Magunitude"))),
        depth_km=_float(item.get("Depth")),
        max_intensity=(str(item["MaxIntensity"]) if item.get("MaxIntensity") is not None else None),
        status=status,
        is_cancelled=status == EventStatus.cancelled,
    )


def _parse_cenc_list_item(item: dict[str, Any]) -> ParsedReport:
    origin_time = _parse_time(item["time"])
    event_id = str(item.get("md5") or sha256(str(sorted(item.items())).encode()).hexdigest())
    status = _status(item)
    return ParsedReport(
        source="cenc_eqlist",
        source_event_id=event_id,
        report_number=1,
        report_time=origin_time,
        origin_time=origin_time,
        hypocenter=str(item.get("location") or item.get("placeName") or "未知震中"),
        latitude=float(item["latitude"]),
        longitude=float(item["longitude"]),
        magnitude=_float(item.get("magnitude")),
        depth_km=_float(item.get("depth")),
        max_intensity=(str(item["intensity"]) if item.get("intensity") not in {None, ""} else None),
        status=status,
        is_cancelled=False,
    )


def parse_payload(payload: dict[str, Any], source_hint: str | None = None) -> list[ParsedReport]:
    source = str(payload.get("type") or source_hint or "")
    if source == "heartbeat" or source == "pong":
        return []
    if source not in SUPPORTED_SOURCES:
        return []
    if source != "cenc_eqlist":
        return [_parse_eew(source, payload)]

    if isinstance(payload.get("data"), list):
        items = payload["data"]
    else:
        items = [
            value
            for key, value in payload.items()
            if key.lower().startswith("no") and isinstance(value, dict)
        ]
    return [_parse_cenc_list_item(item) for item in items]
