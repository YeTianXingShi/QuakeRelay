import asyncio
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import decrypt_json
from .db import SessionLocal
from .events import broker
from .models import (
    DeliveryAttempt,
    Earthquake,
    ImpactEstimate,
    JobStatus,
    NotificationJob,
    WebhookEndpoint,
    uuid4_str,
)

RETRY_DELAYS_SECONDS = [15, 60, 300, 900, 1800, 3600, 7200, 14400, 28800, 43200]
CHINA_TZ = timezone(timedelta(hours=8))


def _utc_iso(value: datetime) -> str:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat()


def _china_time(value: str | None) -> str:
    if not value:
        return "未知"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def telegram_message(payload: dict[str, Any]) -> str:
    kind = str(payload.get("kind", ""))
    if kind == "system.test":
        return "✅ QuakeRelay Telegram 测试成功"
    if kind.startswith("system."):
        titles = {
            "system.source_down": "⚠️ 地震数据源异常",
            "system.source_recovered": "✅ 地震数据源已恢复",
        }
        details = payload.get("details") or {}
        lines = [titles.get(kind, "ℹ️ QuakeRelay 系统通知")]
        if details.get("source"):
            lines.append(f"数据源：{details['source']}")
        if details.get("error"):
            lines.append(f"错误：{str(details['error'])[:500]}")
        return "\n".join(lines)[:4000]

    event = payload.get("event") or {}
    titles = {
        "earthquake.initial": "🌏 地震提醒",
        "earthquake.update": "🔄 地震信息更新",
        "earthquake.cancelled": "✅ 地震信息取消",
    }
    lines = [titles.get(kind, "🌏 地震信息")]
    depth = f"{event['depth_km']} km" if event.get("depth_km") is not None else "未知"
    lines.extend(
        [
            f"震中：{event.get('hypocenter') or '未知'}",
            f"时间：{_china_time(event.get('origin_time'))}（北京时间）",
            f"震级：{event.get('magnitude') if event.get('magnitude') is not None else '未知'}",
            f"深度：{depth}",
            f"状态：{event.get('status') or '未知'}",
        ]
    )
    impacts = payload.get("impacts") or []
    if impacts:
        lines.append("")
        lines.append("关注地点预计影响：")
        status_labels = {
            "insufficient_data": "数据不足，暂无法估算",
            "out_of_range": "超出模型适用范围",
            "failed": "估算失败",
        }
        for impact in impacts:
            if impact.get("estimation_status") == "estimated":
                intensity = (
                    f"预计烈度 {impact.get('estimated_intensity')}"
                    f"（{impact.get('intensity_level')}度）"
                )
            else:
                intensity = status_labels.get(impact.get("estimation_status"), "暂无法估算")
            lines.append(
                f"• {impact.get('name') or '未命名地点'}：距震中 "
                f"{impact.get('distance_km', '?')} km，{intensity}"
            )
    sources = event.get("sources") or []
    if sources:
        lines.append(f"来源：{', '.join(sources)}")
    if payload.get("delayed"):
        lines.append("注意：这是断线恢复后的延迟通知。")
    lines.extend(["", "第三方数据与模型估算，仅供辅助参考，请以官方信息为准。"])
    return "\n".join(lines)[:4000]


def telegram_request(config: dict[str, Any], payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    token = str(config["bot_token"])
    body: dict[str, Any] = {
        "chat_id": config["chat_id"],
        "text": telegram_message(payload),
        "disable_notification": bool(config.get("disable_notification", False)),
    }
    if config.get("message_thread_id") is not None:
        body["message_thread_id"] = config["message_thread_id"]
    return f"https://api.telegram.org/bot{token}/sendMessage", body


def build_event_payload(
    session: Session,
    event: Earthquake,
    *,
    kind: str,
    changes: dict[str, Any],
    delayed: bool = False,
) -> dict[str, Any]:
    impacts = session.scalars(
        select(ImpactEstimate).where(
            ImpactEstimate.earthquake_id == event.id,
            ImpactEstimate.revision == event.revision,
            ImpactEstimate.triggered.is_(True),
        )
    ).all()
    sources = sorted({report.source for report in event.reports})
    return {
        "schema_version": "1.0",
        "notification_id": uuid4_str(),
        "kind": kind,
        "sent_at": datetime.now(UTC).isoformat(),
        "delayed": delayed,
        "event": {
            "event_id": event.id,
            "revision": event.revision,
            "status": event.status.value,
            "origin_time": _utc_iso(event.origin_time),
            "hypocenter": event.hypocenter,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "magnitude": event.magnitude,
            "depth_km": event.depth_km,
            "sources": sources,
        },
        "impacts": [
            {
                "location_id": impact.location_id,
                "name": impact.location_name,
                "distance_km": impact.epicentral_distance_km,
                "hypocentral_distance_km": impact.hypocentral_distance_km,
                "estimated_intensity": impact.estimated_intensity,
                "intensity_level": impact.intensity_level,
                "confidence": impact.confidence,
                "estimation_status": impact.estimation_status,
            }
            for impact in impacts
        ],
        "changes": changes,
        "disclaimer": "第三方数据与模型估算，仅供辅助参考，请以官方信息为准。",
    }


def enqueue_for_all_endpoints(
    session: Session,
    *,
    event: Earthquake,
    kind: str,
    changes: dict[str, Any],
    delayed: bool = False,
) -> int:
    endpoints = session.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.enabled.is_(True))
    ).all()
    if not endpoints:
        return 0
    payload = build_event_payload(session, event, kind=kind, changes=changes, delayed=delayed)
    count = 0
    for endpoint in endpoints:
        key = f"{event.id}:{event.revision}:{kind}"
        existing = session.scalar(
            select(NotificationJob.id).where(
                NotificationJob.endpoint_id == endpoint.id,
                NotificationJob.idempotency_key == key,
            )
        )
        if existing:
            continue
        session.add(
            NotificationJob(
                endpoint_id=endpoint.id,
                earthquake_id=event.id,
                idempotency_key=key,
                kind=kind,
                payload=payload,
            )
        )
        count += 1
    return count


def enqueue_system_notification(session: Session, kind: str, details: dict[str, Any]) -> None:
    endpoints = session.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.enabled.is_(True))
    ).all()
    minute = datetime.now(UTC).strftime("%Y%m%d%H%M")
    for endpoint in endpoints:
        key = f"system:{kind}:{minute}"
        session.add(
            NotificationJob(
                endpoint_id=endpoint.id,
                idempotency_key=key,
                kind=kind,
                payload={
                    "schema_version": "1.0",
                    "notification_id": uuid4_str(),
                    "kind": kind,
                    "sent_at": datetime.now(UTC).isoformat(),
                    "details": details,
                },
            )
        )


class NotificationWorker:
    def __init__(self) -> None:
        self._stop = asyncio.Event()

    async def run(self) -> None:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            while not self._stop.is_set():
                jobs = self._claim_jobs()
                if not jobs:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=2)
                    except TimeoutError:
                        continue
                for job_id in jobs:
                    await self._deliver(client, job_id)

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _claim_jobs() -> list[str]:
        with SessionLocal() as session, session.begin():
            now = datetime.now(UTC)
            jobs = session.scalars(
                select(NotificationJob)
                .where(
                    NotificationJob.status.in_([JobStatus.pending, JobStatus.processing]),
                    NotificationJob.next_attempt_at <= now,
                    NotificationJob.attempts < 10,
                )
                .order_by(NotificationJob.created_at)
                .limit(10)
            ).all()
            ids: list[str] = []
            for job in jobs:
                job.status = JobStatus.processing
                ids.append(job.id)
            return ids

    async def _deliver(self, client: httpx.AsyncClient, job_id: str) -> None:
        with SessionLocal() as session:
            job = session.get(NotificationJob, job_id)
            if not job:
                return
            endpoint = job.endpoint
            telegram_config: dict[str, Any] | None = None
            started = time.monotonic()
            status_code: int | None = None
            excerpt: str | None = None
            error: str | None = None
            try:
                if endpoint.channel_type == "telegram":
                    telegram_config = decrypt_json(endpoint.encrypted_config)
                    request_url, request_body = telegram_request(telegram_config, job.payload)
                    headers = {"Content-Type": "application/json"}
                else:
                    request_url = endpoint.url
                    request_body = job.payload
                    headers = {
                        "Content-Type": "application/json",
                        **decrypt_json(endpoint.encrypted_headers),
                    }
                headers["Idempotency-Key"] = job.idempotency_key
                response = await client.post(
                    request_url,
                    headers=headers,
                    json=request_body,
                    timeout=endpoint.timeout_seconds,
                )
                status_code = response.status_code
                excerpt = (
                    f"{response.headers.get('content-type', 'unknown')}; "
                    f"{len(response.content)} bytes"
                )
                response.raise_for_status()
                if endpoint.channel_type == "telegram" and not response.json().get("ok"):
                    raise RuntimeError("Telegram API returned ok=false")
            except Exception as exc:  # delivery errors are persisted and retried
                error = str(exc)[:1000]
                if telegram_config and telegram_config.get("bot_token"):
                    error = error.replace(str(telegram_config["bot_token"]), "<redacted>")
            duration = int((time.monotonic() - started) * 1000)

            job.attempts += 1
            session.add(
                DeliveryAttempt(
                    job_id=job.id,
                    attempt_number=job.attempts,
                    duration_ms=duration,
                    status_code=status_code,
                    response_excerpt=excerpt,
                    error=error,
                )
            )
            if error is None:
                job.status = JobStatus.delivered
                job.delivered_at = datetime.now(UTC)
                job.last_error = None
            elif job.attempts >= 10:
                job.status = JobStatus.failed
                job.last_error = error
            else:
                job.status = JobStatus.pending
                job.last_error = error
                job.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=RETRY_DELAYS_SECONDS[job.attempts - 1]
                )
            session.commit()
        await broker.publish({"type": "delivery", "job_id": job_id})
