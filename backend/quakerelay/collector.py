import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import websockets
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .events import broker
from .ingest import ingest_payload
from .models import SourceHealth
from .notifications import enqueue_system_notification, enqueue_weather_notification
from .sources import LOGICAL_SOURCES
from .weather import ingest_weather_payload, latest_is_notifiable, weather_matches

logger = logging.getLogger(__name__)
WS_URL = "wss://ws-api.wolfx.jp/all_eew"
WEATHER_URL = "https://api.wolfx.jp/weather_rank.json"
WEATHER_HEALTH_KEY = "http:weather_rank"
HTTP_SOURCES = {
    "sc_eew": "https://api.wolfx.jp/sc_eew.json",
    "fj_eew": "https://api.wolfx.jp/fj_eew.json",
    "cq_eew": "https://api.wolfx.jp/cq_eew.json",
    "cenc_eew": "https://api.wolfx.jp/cenc_eew.json",
    "cenc_eqlist": "https://api.wolfx.jp/cenc_eqlist.json",
}
QUERY_COMMANDS = {
    "sc_eew": "query_sceew",
    "fj_eew": "query_fjeew",
    "cq_eew": "query_cqeew",
    "cenc_eew": "query_cenceew",
    "cenc_eqlist": "query_cenceqlist",
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class WolfxCollector:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._connected_since: datetime | None = None

    async def run(self) -> None:
        self._initialize_health_rows()
        tasks = [
            asyncio.create_task(self._websocket_loop(), name="wolfx-websocket"),
            asyncio.create_task(self._http_loop(), name="wolfx-http"),
            asyncio.create_task(self._weather_loop(), name="wolfx-weather"),
            asyncio.create_task(self._health_loop(), name="wolfx-health"),
        ]
        try:
            await self._stop.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self) -> None:
        self._stop.set()

    async def _websocket_loop(self) -> None:
        backoff = 1
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    WS_URL, open_timeout=15, close_timeout=5, ping_interval=None
                ) as websocket:
                    self._connected_since = datetime.now(UTC)
                    self._set_ws_health(connected=True, error=None)
                    await broker.publish({"type": "source_health", "connected": True})
                    for expected_source, command in QUERY_COMMANDS.items():
                        await self._query_initial_snapshot(expected_source, command)
                    backoff = 1
                    while not self._stop.is_set():
                        raw = await asyncio.wait_for(websocket.recv(), timeout=90)
                        payload = json.loads(raw)
                        if payload.get("type") == "heartbeat":
                            self._set_ws_health(
                                connected=True, heartbeat=True, latest_payload=payload
                            )
                            await broker.publish(
                                {
                                    "type": "source_health",
                                    "source": "wolfx_ws",
                                    "last_heartbeat_at": datetime.now(UTC).isoformat(),
                                }
                            )
                            await websocket.send("ping")
                            continue
                        await self._ingest(payload, channel="ws")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Wolfx WebSocket disconnected: %s", exc)
                self._set_ws_health(connected=False, error=str(exc))
                await broker.publish({"type": "source_health", "connected": False})
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except TimeoutError:
                    pass
                backoff = min(60, backoff * 2)

    async def _query_initial_snapshot(self, source: str, command: str) -> None:
        """Fetch one startup snapshot without burst-query loss on all_eew."""
        url = f"wss://ws-api.wolfx.jp/{source}"
        for attempt in range(1, 3):
            try:
                async with websockets.connect(
                    url, open_timeout=15, close_timeout=5, ping_interval=None
                ) as websocket:
                    # Dedicated endpoints send a heartbeat immediately after connection.
                    await asyncio.wait_for(websocket.recv(), timeout=10)
                    await websocket.send(command)
                    while not self._stop.is_set():
                        payload = json.loads(
                            await asyncio.wait_for(websocket.recv(), timeout=10)
                        )
                        if payload.get("type") == source:
                            await self._ingest(payload, channel="ws")
                            return
            except (TimeoutError, OSError, websockets.WebSocketException) as exc:
                logger.warning(
                    "Wolfx initial WebSocket query failed for %s (attempt %d/2): %s",
                    source,
                    attempt,
                    exc,
                )

    async def _http_loop(self) -> None:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            while not self._stop.is_set():
                for source, url in HTTP_SOURCES.items():
                    if self._stop.is_set():
                        return
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        payload = response.json()
                        if isinstance(payload, dict):
                            await self._ingest(payload, source, channel="http")
                    except Exception as exc:
                        logger.warning("Wolfx HTTP sync failed for %s: %s", source, exc)
                        self._set_channel_health(f"http:{source}", connected=False, error=str(exc))
                        await broker.publish({"type": "source_health", "source": f"http:{source}"})
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=60)
                except TimeoutError:
                    pass

    async def _weather_loop(self) -> None:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            while not self._stop.is_set():
                try:
                    response = await client.get(WEATHER_URL)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("weather_rank response must be a JSON object")
                    with SessionLocal() as session, session.begin():
                        health = self._get_health(session, WEATHER_HEALTH_KEY)
                        health.connected = True
                        health.last_message_at = datetime.now(UTC)
                        health.last_error = None
                        health.latest_payload = payload
                        health.updated_at = datetime.now(UTC)
                        _, latest = ingest_weather_payload(session, payload)
                        session.flush()
                        if latest and latest_is_notifiable(latest):
                            enqueue_weather_notification(
                                session, latest, weather_matches(session, latest)
                            )
                    await broker.publish(
                        {"type": "weather", "source": WEATHER_HEALTH_KEY}
                    )
                    await broker.publish(
                        {"type": "source_health", "source": WEATHER_HEALTH_KEY}
                    )
                except Exception as exc:
                    logger.warning("Wolfx weather sync failed: %s", exc)
                    self._set_channel_health(
                        WEATHER_HEALTH_KEY, connected=False, error=str(exc)
                    )
                    await broker.publish(
                        {"type": "source_health", "source": WEATHER_HEALTH_KEY}
                    )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=300)
                except TimeoutError:
                    pass

    async def _ingest(
        self,
        payload: dict[str, Any],
        source_hint: str | None = None,
        *,
        channel: str,
    ) -> None:
        logical_source = str(payload.get("type") or source_hint or "unknown")
        with SessionLocal() as session, session.begin():
            event_ids = ingest_payload(session, payload, source_hint)
            if logical_source in LOGICAL_SOURCES:
                health = self._get_health(session, f"{channel}:{logical_source}")
                health.connected = True
                health.last_message_at = datetime.now(UTC)
                health.last_error = None
                health.latest_payload = payload
                health.updated_at = datetime.now(UTC)
        for event_id in event_ids:
            await broker.publish({"type": "earthquake", "event_id": event_id})
        if logical_source in LOGICAL_SOURCES:
            await broker.publish({"type": "source_health", "source": f"{channel}:{logical_source}"})

    @staticmethod
    def _get_health(session: Session, source: str = "wolfx_ws") -> SourceHealth:
        health = session.get(SourceHealth, source)
        if health is None:
            health = SourceHealth(source=source)
            session.add(health)
        return health

    def _initialize_health_rows(self) -> None:
        with SessionLocal() as session, session.begin():
            self._get_health(session)
            self._get_health(session, WEATHER_HEALTH_KEY)
            for source in LOGICAL_SOURCES:
                self._get_health(session, f"ws:{source}")
                self._get_health(session, f"http:{source}")

    def _set_channel_health(
        self, source: str, *, connected: bool, error: str | None = None
    ) -> None:
        with SessionLocal() as session, session.begin():
            health = self._get_health(session, source)
            health.connected = connected
            health.last_error = error
            health.updated_at = datetime.now(UTC)

    def _set_ws_health(
        self,
        *,
        connected: bool,
        error: str | None = None,
        heartbeat: bool = False,
        latest_payload: dict[str, Any] | None = None,
    ) -> None:
        with SessionLocal() as session, session.begin():
            health = self._get_health(session)
            was_out = health.outage_notified
            health.connected = connected
            health.last_error = error
            health.updated_at = datetime.now(UTC)
            if connected:
                health.last_message_at = datetime.now(UTC)
            if heartbeat:
                health.last_heartbeat_at = datetime.now(UTC)
            if latest_payload is not None:
                health.latest_payload = latest_payload
            if connected and was_out:
                health.outage_notified = False
                enqueue_system_notification(
                    session,
                    "system.source_recovered",
                    {"source": "wolfx_ws", "recovered_at": datetime.now(UTC).isoformat()},
                )
            for source in LOGICAL_SOURCES:
                logical_health = self._get_health(session, f"ws:{source}")
                logical_health.connected = connected
                logical_health.updated_at = datetime.now(UTC)
                if error:
                    logical_health.last_error = error
                elif connected:
                    logical_health.last_error = None

    async def _health_loop(self) -> None:
        threshold = timedelta(minutes=get_settings().source_down_minutes)
        while not self._stop.is_set():
            with SessionLocal() as session, session.begin():
                health = self._get_health(session)
                updated = _aware(health.updated_at)
                if not health.connected and updated and datetime.now(UTC) - updated >= threshold:
                    if not health.outage_notified:
                        enqueue_system_notification(
                            session,
                            "system.source_down",
                            {
                                "source": "wolfx_ws",
                                "since": updated.isoformat(),
                                "error": health.last_error,
                            },
                        )
                        health.outage_notified = True
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30)
            except TimeoutError:
                pass
