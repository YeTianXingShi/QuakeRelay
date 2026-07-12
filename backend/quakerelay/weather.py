import hashlib
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Location, WeatherSnapshot

CHINA_TZ = timezone(timedelta(hours=8))
HOUR_KEY = re.compile(r"^\d{12}$")
ADMIN_SUFFIXES = (
    "特别行政区",
    "自治州",
    "自治县",
    "自治区",
    "地区",
    "盟",
    "省",
    "市",
    "区",
    "县",
    "旗",
)
RANK_FIELDS = {
    "temperature": "temperature_rank",
    "rain": "rain_rank",
    "wind": "wind_rank",
}
PROVINCE_ALIASES = {
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "香港特别行政区": "香港",
    "澳门特别行政区": "澳门",
}


def normalize_admin_name(value: str) -> str:
    result = re.sub(r"\s+", "", value or "")
    result = PROVINCE_ALIASES.get(result, result)
    changed = True
    while changed and result:
        changed = False
        for suffix in ADMIN_SUFFIXES:
            if result.endswith(suffix) and len(result) > len(suffix):
                result = result[: -len(suffix)]
                changed = True
                break
    return result


def location_matches_station(location: Location, province: str, station: str) -> bool:
    if not location.province or not (location.city or location.district):
        return False
    if normalize_admin_name(location.province) != normalize_admin_name(province):
        return False
    station_name = normalize_admin_name(station)
    candidates = [normalize_admin_name(location.city), normalize_admin_name(location.district)]
    return any(
        candidate and (candidate in station_name or station_name in candidate)
        for candidate in candidates
    )


def hour_key_to_utc(hour_key: str) -> datetime:
    local = datetime.strptime(hour_key, "%Y%m%d%H%M").replace(tzinfo=CHINA_TZ)
    return local.astimezone(UTC)


def _rank_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def ingest_weather_payload(
    session: Session, payload: dict[str, Any]
) -> tuple[list[WeatherSnapshot], WeatherSnapshot | None]:
    snapshots: list[WeatherSnapshot] = []
    for hour_key, raw in payload.items():
        if not HOUR_KEY.fullmatch(hour_key) or not isinstance(raw, dict):
            continue
        normalized: dict[str, list[dict[str, Any]]] = {
            "temperature_rank": _rank_entries(raw.get("tempRank")),
            "rain_rank": _rank_entries(raw.get("rainRank")),
            "wind_rank": _rank_entries(raw.get("windSRank")),
        }
        content_hash = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        snapshot = session.scalar(
            select(WeatherSnapshot).where(WeatherSnapshot.hour_key == hour_key)
        )
        if snapshot is None:
            snapshot = WeatherSnapshot(
                hour_key=hour_key,
                observed_at=hour_key_to_utc(hour_key),
                content_hash=content_hash,
                **normalized,
            )
            session.add(snapshot)
        elif snapshot.content_hash != content_hash:
            snapshot.temperature_rank = normalized["temperature_rank"]
            snapshot.rain_rank = normalized["rain_rank"]
            snapshot.wind_rank = normalized["wind_rank"]
            snapshot.content_hash = content_hash
            snapshot.updated_at = datetime.now(UTC)
        snapshots.append(snapshot)
    latest = max(snapshots, key=lambda item: item.hour_key, default=None)
    return snapshots, latest


def weather_matches(session: Session, snapshot: WeatherSnapshot) -> list[dict[str, Any]]:
    locations = session.scalars(
        select(Location).where(Location.enabled.is_(True), Location.deleted_at.is_(None))
    ).all()
    matches: list[dict[str, Any]] = []
    for kind, field in RANK_FIELDS.items():
        entries = getattr(snapshot, field)
        for rank, entry in enumerate(entries, start=1):
            province = str(entry.get("province") or "")
            station = str(entry.get("city") or "")
            matched = [
                location
                for location in locations
                if location_matches_station(location, province, station)
            ]
            if matched:
                matches.append(
                    {
                        "kind": kind,
                        "rank": rank,
                        "province": province,
                        "city": station,
                        "value": str(entry.get("value") or ""),
                        "location_ids": [location.id for location in matched],
                        "location_names": [location.name for location in matched],
                    }
                )
    return matches


def latest_is_notifiable(snapshot: WeatherSnapshot, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    observed = snapshot.observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    age = current - observed.astimezone(UTC)
    return timedelta(0) <= age <= timedelta(hours=2)
