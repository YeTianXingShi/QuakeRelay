from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .backup import create_sqlite_backup
from .config import get_settings
from .crypto import encrypt_json
from .db import get_db
from .events import broker
from .fusion import fusion_service
from .geo import gcj02_to_wgs84, wgs84_to_gcj02
from .models import (
    DeliveryAttempt,
    Earthquake,
    ImpactEstimate,
    JobStatus,
    Location,
    NotificationJob,
    SourceHealth,
    SourceReport,
    WeatherSnapshot,
    WebhookEndpoint,
    uuid4_str,
)
from .schemas import (
    LocationCreate,
    LocationUpdate,
    TelegramCreate,
    WebhookCreate,
    WebhookUpdate,
)
from .sources import source_descriptor
from .weather import weather_matches

router = APIRouter(prefix="/api/v1")


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _event_summary(event: Earthquake, impacts: list[ImpactEstimate]) -> dict[str, Any]:
    gcj_lat, gcj_lon = wgs84_to_gcj02(event.latitude, event.longitude)
    return {
        "id": event.id,
        "origin_time": _utc(event.origin_time),
        "hypocenter": event.hypocenter,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "gcj02_latitude": gcj_lat,
        "gcj02_longitude": gcj_lon,
        "magnitude": event.magnitude,
        "depth_km": event.depth_km,
        "status": event.status.value,
        "revision": event.revision,
        "latest_source": event.latest_source,
        "affected_locations": sum(1 for item in impacts if item.triggered),
        "max_estimated_intensity": max(
            (item.estimated_intensity for item in impacts if item.estimated_intensity is not None),
            default=None,
        ),
    }


@router.get("/health")
def health(session: Session = Depends(get_db)) -> dict[str, Any]:
    session.execute(select(1))
    return {"status": "ok", "time": datetime.now(UTC), "version": "0.1.0"}


@router.get("/overview")
def overview(session: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "event_count": session.scalar(select(func.count(Earthquake.id))) or 0,
        "location_count": session.scalar(select(func.count(Location.id))) or 0,
        "failed_deliveries": session.scalar(
            select(func.count(NotificationJob.id)).where(NotificationJob.status == JobStatus.failed)
        )
        or 0,
        "sources": [
            dict(
                {
                    "source": row.source,
                    "channel": source_descriptor(row.source).channel,
                    "logical_source": source_descriptor(row.source).logical_source,
                    "display_name": source_descriptor(row.source).display_name,
                    "connected": row.connected,
                    "last_message_at": _utc(row.last_message_at),
                    "last_heartbeat_at": _utc(row.last_heartbeat_at),
                    "last_error": row.last_error,
                }
            )
            for row in session.scalars(select(SourceHealth).order_by(SourceHealth.source)).all()
        ],
    }


@router.get("/sources")
def source_statuses(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        {
            "source": row.source,
            "channel": source_descriptor(row.source).channel,
            "logical_source": source_descriptor(row.source).logical_source,
            "display_name": source_descriptor(row.source).display_name,
            "connected": row.connected,
            "last_message_at": _utc(row.last_message_at),
            "last_heartbeat_at": _utc(row.last_heartbeat_at),
            "last_error": row.last_error,
            "updated_at": _utc(row.updated_at),
            "latest_payload": row.latest_payload,
        }
        for row in session.scalars(select(SourceHealth).order_by(SourceHealth.source)).all()
    ]


def _weather_snapshot_dict(
    session: Session, snapshot: WeatherSnapshot
) -> dict[str, Any]:
    matches = weather_matches(session, snapshot)
    by_entry = {
        (str(item["kind"]), int(item["rank"])): item for item in matches
    }

    def ranking(kind: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                **entry,
                "rank": index,
                "matched": (kind, index) in by_entry,
                "location_names": by_entry.get((kind, index), {}).get(
                    "location_names", []
                ),
            }
            for index, entry in enumerate(entries, start=1)
        ]

    return {
        "id": snapshot.id,
        "hour_key": snapshot.hour_key,
        "observed_at": _utc(snapshot.observed_at),
        "temperature_rank": ranking("temperature", snapshot.temperature_rank),
        "rain_rank": ranking("rain", snapshot.rain_rank),
        "wind_rank": ranking("wind", snapshot.wind_rank),
        "content_hash": snapshot.content_hash,
        "updated_at": _utc(snapshot.updated_at),
    }


@router.get("/weather")
def list_weather(
    day: date | None = Query(default=None, alias="date"),
    hour: int | None = Query(default=None, ge=0, le=23),
    limit: int = Query(default=24, ge=1, le=200),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = select(WeatherSnapshot)
    if day is not None:
        prefix = day.strftime("%Y%m%d")
        if hour is None:
            statement = statement.where(WeatherSnapshot.hour_key.like(f"{prefix}%"))
        else:
            statement = statement.where(
                WeatherSnapshot.hour_key == f"{prefix}{hour:02d}00"
            )
    elif hour is not None:
        statement = statement.where(
            func.substr(WeatherSnapshot.hour_key, 9, 2) == f"{hour:02d}"
        )
    snapshots = session.scalars(
        statement.order_by(WeatherSnapshot.hour_key.desc()).limit(limit)
    ).all()
    return {
        "items": [_weather_snapshot_dict(session, snapshot) for snapshot in snapshots]
    }


@router.get("/config/public")
def public_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "amap_js_key": settings.amap_js_key,
        "amap_security_code": settings.amap_security_code,
        "timezone": "Asia/Shanghai",
        "disclaimer": "Wolfx 第三方数据与模型估算，仅供辅助参考，请以官方信息为准。",
    }


@router.get("/events")
def list_events(
    limit: int = Query(30, ge=1, le=100),
    cursor: str | None = None,
    q: str | None = None,
    min_magnitude: float | None = None,
    source: str | None = None,
    status: str | None = None,
    affected: bool | None = None,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = select(Earthquake).options(selectinload(Earthquake.impacts))
    filters: list[Any] = []
    if cursor:
        cursor_event = session.get(Earthquake, cursor)
        if cursor_event:
            filters.append(
                or_(
                    Earthquake.origin_time < cursor_event.origin_time,
                    and_(
                        Earthquake.origin_time == cursor_event.origin_time,
                        Earthquake.id < cursor_event.id,
                    ),
                )
            )
    if q:
        filters.append(Earthquake.hypocenter.contains(q))
    if min_magnitude is not None:
        filters.append(Earthquake.magnitude >= min_magnitude)
    if status:
        filters.append(Earthquake.status == status)
    if source:
        filters.append(Earthquake.reports.any(SourceReport.source == source))
    if affected is not None:
        criterion = Earthquake.impacts.any(ImpactEstimate.triggered.is_(True))
        filters.append(criterion if affected else ~criterion)
    if filters:
        statement = statement.where(*filters)
    events = session.scalars(
        statement.order_by(Earthquake.origin_time.desc(), Earthquake.id.desc()).limit(limit + 1)
    ).all()
    has_more = len(events) > limit
    page = events[:limit]
    return {
        "items": [_event_summary(event, event.impacts) for event in page],
        "next_cursor": page[-1].id if has_more and page else None,
    }


@router.get("/events/{event_id}")
def event_detail(event_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    event = session.scalar(
        select(Earthquake)
        .where(Earthquake.id == event_id)
        .options(
            selectinload(Earthquake.impacts).selectinload(ImpactEstimate.location),
            selectinload(Earthquake.reports),
            selectinload(Earthquake.revisions),
        )
    )
    if not event:
        raise HTTPException(404, "Event not found")
    current_impacts = [item for item in event.impacts if item.revision == event.revision]
    result = _event_summary(event, current_impacts)
    result.update(
        {
            "impacts": [
                dict(
                    {
                        "location_id": impact.location_id,
                        "location_name": impact.location_name,
                        "latitude": impact.location_latitude,
                        "longitude": impact.location_longitude,
                        "distance_km": impact.epicentral_distance_km,
                        "estimated_intensity": impact.estimated_intensity,
                        "intensity_level": impact.intensity_level,
                        "confidence": impact.confidence,
                        "triggered": impact.triggered,
                        "model_version": impact.model_version,
                        "estimation_status": impact.estimation_status,
                    },
                    **{
                        "gcj02_latitude": wgs84_to_gcj02(
                            impact.location_latitude, impact.location_longitude
                        )[0],
                        "gcj02_longitude": wgs84_to_gcj02(
                            impact.location_latitude, impact.location_longitude
                        )[1],
                    },
                )
                for impact in current_impacts
            ],
            "reports": [
                {
                    "id": report.id,
                    "source": report.source,
                    "source_event_id": report.source_event_id,
                    "report_number": report.report_number,
                    "report_time": _utc(report.report_time),
                    "origin_time": _utc(report.origin_time),
                    "hypocenter": report.hypocenter,
                    "magnitude": report.magnitude,
                    "depth_km": report.depth_km,
                    "status": report.status.value,
                }
                for report in sorted(event.reports, key=lambda row: row.report_time)
            ],
            "revisions": [
                {
                    "revision": revision.revision,
                    "snapshot": revision.snapshot,
                    "changes": revision.changes,
                    "created_at": _utc(revision.created_at),
                }
                for revision in sorted(event.revisions, key=lambda row: row.revision)
            ],
        }
    )
    return result


def _location_dict(location: Location) -> dict[str, Any]:
    gcj_lat, gcj_lon = wgs84_to_gcj02(location.latitude, location.longitude)
    return {
        "id": location.id,
        "name": location.name,
        "address": location.address,
        "province": location.province,
        "city": location.city,
        "district": location.district,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "gcj02_latitude": gcj_lat,
        "gcj02_longitude": gcj_lon,
        "enabled": location.enabled,
    }


@router.get("/locations")
def list_locations(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        _location_dict(row)
        for row in session.scalars(select(Location).where(Location.deleted_at.is_(None))).all()
    ]


@router.post("/locations", status_code=201)
def create_location(body: LocationCreate, session: Session = Depends(get_db)) -> dict[str, Any]:
    lat, lon = body.latitude, body.longitude
    if body.coordinate_system == "gcj02":
        lat, lon = gcj02_to_wgs84(lat, lon)
    location = Location(
        name=body.name,
        address=body.address,
        province=body.province,
        city=body.city,
        district=body.district,
        latitude=lat,
        longitude=lon,
        enabled=body.enabled,
    )
    session.add(location)
    session.flush()
    fusion_service.recalculate_location(session, location)
    session.commit()
    return _location_dict(location)


@router.patch("/locations/{location_id}")
def update_location(
    location_id: str, body: LocationUpdate, session: Session = Depends(get_db)
) -> dict[str, Any]:
    location = session.get(Location, location_id)
    if not location:
        raise HTTPException(404, "Location not found")
    values = body.model_dump(exclude_unset=True)
    coordinate_system = values.pop("coordinate_system", body.coordinate_system)
    for key in ("name", "address", "province", "city", "district", "enabled"):
        if key in values:
            setattr(location, key, values[key])
    if "latitude" in values or "longitude" in values:
        lat = values.get("latitude", location.latitude)
        lon = values.get("longitude", location.longitude)
        if coordinate_system == "gcj02":
            lat, lon = gcj02_to_wgs84(lat, lon)
        location.latitude, location.longitude = lat, lon
    fusion_service.recalculate_location(session, location)
    session.commit()
    return _location_dict(location)


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: str, session: Session = Depends(get_db)) -> None:
    location = session.get(Location, location_id)
    if not location:
        raise HTTPException(404, "Location not found")
    jobs = session.scalars(
        select(NotificationJob).where(NotificationJob.earthquake_id.is_not(None))
    ).all()
    for job in jobs:
        impacts = job.payload.get("impacts")
        if not isinstance(impacts, list):
            continue
        retained = [
            impact
            for impact in impacts
            if not isinstance(impact, dict) or impact.get("location_id") != location_id
        ]
        if len(retained) != len(impacts):
            job.payload = {**job.payload, "impacts": retained}
    for impact in session.scalars(
        select(ImpactEstimate).where(ImpactEstimate.location_id == location_id)
    ).all():
        session.delete(impact)
    session.flush()
    session.delete(location)
    session.commit()


def _webhook_dict(endpoint: WebhookEndpoint) -> dict[str, Any]:
    from .crypto import decrypt_json

    headers = decrypt_json(endpoint.encrypted_headers)
    config = decrypt_json(endpoint.encrypted_config)
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "channel_type": endpoint.channel_type,
        "url": endpoint.url if endpoint.channel_type == "generic" else None,
        "header_names": sorted(headers),
        "chat_id": config.get("chat_id") if endpoint.channel_type == "telegram" else None,
        "message_thread_id": (
            config.get("message_thread_id") if endpoint.channel_type == "telegram" else None
        ),
        "disable_notification": (
            bool(config.get("disable_notification"))
            if endpoint.channel_type == "telegram"
            else False
        ),
        "has_bot_token": bool(config.get("bot_token")),
        "timeout_seconds": endpoint.timeout_seconds,
        "enabled": endpoint.enabled,
        "earthquake_enabled": endpoint.earthquake_enabled,
        "weather_enabled": endpoint.weather_enabled,
    }


@router.get("/webhooks")
def list_webhooks(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [_webhook_dict(row) for row in session.scalars(select(WebhookEndpoint)).all()]


@router.post("/webhooks", status_code=201)
def create_webhook(body: WebhookCreate, session: Session = Depends(get_db)) -> dict[str, Any]:
    endpoint = WebhookEndpoint(
        name=body.name,
        channel_type="generic",
        url=str(body.url),
        encrypted_headers=encrypt_json(body.headers),
        timeout_seconds=body.timeout_seconds,
        enabled=body.enabled,
        earthquake_enabled=body.earthquake_enabled,
        weather_enabled=body.weather_enabled,
    )
    session.add(endpoint)
    session.commit()
    return _webhook_dict(endpoint)


@router.post("/webhooks/telegram", status_code=201)
def create_telegram(body: TelegramCreate, session: Session = Depends(get_db)) -> dict[str, Any]:
    endpoint = WebhookEndpoint(
        name=body.name,
        channel_type="telegram",
        url="telegram://sendMessage",
        encrypted_headers=encrypt_json({}),
        encrypted_config=encrypt_json(
            {
                "bot_token": body.bot_token,
                "chat_id": body.chat_id,
                "message_thread_id": body.message_thread_id,
                "disable_notification": body.disable_notification,
            }
        ),
        timeout_seconds=body.timeout_seconds,
        enabled=body.enabled,
        earthquake_enabled=body.earthquake_enabled,
        weather_enabled=body.weather_enabled,
    )
    session.add(endpoint)
    session.commit()
    return _webhook_dict(endpoint)


@router.patch("/webhooks/{endpoint_id}")
def update_webhook(
    endpoint_id: str, body: WebhookUpdate, session: Session = Depends(get_db)
) -> dict[str, Any]:
    endpoint = session.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(404, "Webhook not found")
    values = body.model_dump(exclude_unset=True)
    if "headers" in values:
        endpoint.encrypted_headers = encrypt_json(values.pop("headers"))
    if "url" in values:
        values["url"] = str(values["url"])
    for key, value in values.items():
        setattr(endpoint, key, value)
    session.commit()
    return _webhook_dict(endpoint)


@router.delete("/webhooks/{endpoint_id}", status_code=204)
def delete_webhook(endpoint_id: str, session: Session = Depends(get_db)) -> None:
    endpoint = session.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(404, "Webhook not found")
    jobs = session.scalars(
        select(NotificationJob).where(NotificationJob.endpoint_id == endpoint_id)
    ).all()
    for job in jobs:
        for attempt in session.scalars(
            select(DeliveryAttempt).where(DeliveryAttempt.job_id == job.id)
        ).all():
            session.delete(attempt)
        session.delete(job)
    session.delete(endpoint)
    session.commit()


@router.post("/webhooks/{endpoint_id}/test", status_code=202)
def test_webhook(endpoint_id: str, session: Session = Depends(get_db)) -> dict[str, str]:
    endpoint = session.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(404, "Webhook not found")
    job = NotificationJob(
        endpoint_id=endpoint.id,
        idempotency_key=f"test:{uuid4_str()}",
        kind="system.test",
        payload={
            "schema_version": "1.0",
            "notification_id": uuid4_str(),
            "kind": "system.test",
            "sent_at": datetime.now(UTC).isoformat(),
            "details": {"message": "QuakeRelay Webhook 测试成功"},
        },
    )
    session.add(job)
    session.commit()
    return {"job_id": job.id}


@router.get("/deliveries")
def list_deliveries(
    limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    jobs = session.scalars(
        select(NotificationJob)
        .options(selectinload(NotificationJob.endpoint))
        .order_by(NotificationJob.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": job.id,
            "endpoint_name": job.endpoint.name,
            "kind": job.kind,
            "status": job.status.value,
            "attempts": job.attempts,
            "last_error": job.last_error,
            "created_at": _utc(job.created_at),
            "delivered_at": _utc(job.delivered_at),
        }
        for job in jobs
    ]


@router.post("/deliveries/{job_id}/retry", status_code=202)
def retry_delivery(job_id: str, session: Session = Depends(get_db)) -> dict[str, str]:
    job = session.get(NotificationJob, job_id)
    if not job:
        raise HTTPException(404, "Delivery not found")
    job.status = JobStatus.pending
    job.attempts = 0
    job.next_attempt_at = datetime.now(UTC)
    job.last_error = None
    session.commit()
    return {"status": "queued"}


@router.get("/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(broker.subscribe(), media_type="text/event-stream")


@router.post("/backups", status_code=201)
def create_backup() -> dict[str, Any]:
    try:
        return create_sqlite_backup()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
