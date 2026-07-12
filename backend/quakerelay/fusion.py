from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .geo import haversine_km
from .intensity import ChinaRegionalIntensityModel, IntensityResult
from .models import (
    Earthquake,
    EventRevision,
    EventStatus,
    ImpactEstimate,
    Location,
    RawMessage,
    SourceReport,
)
from .notifications import enqueue_for_all_endpoints
from .parsers import ParsedReport, parse_payload

SOURCE_PRIORITY = {"sc_eew": 1, "fj_eew": 1, "cq_eew": 1, "cenc_eew": 2, "cenc_eqlist": 3}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _snapshot(event: Earthquake) -> dict[str, Any]:
    return {
        "origin_time": _as_utc(event.origin_time).isoformat(),
        "hypocenter": event.hypocenter,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "magnitude": event.magnitude,
        "depth_km": event.depth_km,
        "status": event.status.value,
        "latest_source": event.latest_source,
    }


def _material_changes(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    old_mag, new_mag = previous.get("magnitude"), current.get("magnitude")
    if (
        old_mag is None
        and new_mag is not None
        or (old_mag is not None and new_mag is not None and abs(new_mag - old_mag) >= 0.3)
    ):
        changes["magnitude"] = {"from": old_mag, "to": new_mag}
    old_depth, new_depth = previous.get("depth_km"), current.get("depth_km")
    if (
        old_depth is None
        and new_depth is not None
        or (old_depth is not None and new_depth is not None and abs(new_depth - old_depth) >= 10)
    ):
        changes["depth_km"] = {"from": old_depth, "to": new_depth}
    distance = haversine_km(
        float(previous["latitude"]),
        float(previous["longitude"]),
        float(current["latitude"]),
        float(current["longitude"]),
    )
    if distance >= 10:
        changes["epicenter"] = {"moved_km": round(distance, 2)}
    if previous.get("status") != current.get("status"):
        changes["status"] = {"from": previous.get("status"), "to": current.get("status")}
    if previous.get("hypocenter") != current.get("hypocenter"):
        changes["hypocenter"] = {
            "from": previous.get("hypocenter"),
            "to": current.get("hypocenter"),
        }
    return changes


class FusionService:
    def __init__(self) -> None:
        self.model = ChinaRegionalIntensityModel()

    def _estimate(self, **kwargs: Any) -> IntensityResult:
        try:
            return self.model.estimate(**kwargs)
        except Exception as exc:
            epicentral = haversine_km(
                kwargs["event_latitude"],
                kwargs["event_longitude"],
                kwargs["location_latitude"],
                kwargs["location_longitude"],
            )
            return IntensityResult(
                epicentral_distance_km=round(epicentral, 2),
                hypocentral_distance_km=round(epicentral, 2),
                estimated_intensity=None,
                intensity_level=None,
                confidence="low",
                model_version=self.model.version,
                triggered=epicentral <= 300,
                status="failed",
                error=str(exc)[:500],
            )

    def process_raw(self, session: Session, raw: RawMessage) -> list[Earthquake]:
        try:
            parsed = parse_payload(raw.payload, raw.source)
        except Exception as exc:
            raw.parse_error = str(exc)[:2000]
            raw.processed_at = datetime.now(UTC)
            return []
        events: list[Earthquake] = []
        for item in parsed:
            report = self._store_report(session, raw, item)
            if report is None:
                continue
            event, changes, is_new = self._merge(session, report)
            self._calculate_impacts(session, event)
            self._append_impact_changes(session, event, changes)
            self._queue_if_needed(session, event, changes, is_new)
            events.append(event)
        raw.processed_at = datetime.now(UTC)
        return events

    @staticmethod
    def _store_report(
        session: Session, raw: RawMessage, parsed: ParsedReport
    ) -> SourceReport | None:
        report = SourceReport(
            raw_message_id=raw.id,
            source=parsed.source,
            source_event_id=parsed.source_event_id,
            report_number=parsed.report_number,
            report_time=parsed.report_time,
            origin_time=parsed.origin_time,
            hypocenter=parsed.hypocenter,
            latitude=parsed.latitude,
            longitude=parsed.longitude,
            magnitude=parsed.magnitude,
            depth_km=parsed.depth_km,
            max_intensity=parsed.max_intensity,
            status=parsed.status,
            is_cancelled=parsed.is_cancelled,
        )
        session.add(report)
        session.flush()
        return report

    def _merge(
        self, session: Session, report: SourceReport
    ) -> tuple[Earthquake, dict[str, Any], bool]:
        previous_link = session.scalar(
            select(SourceReport)
            .where(
                SourceReport.source == report.source,
                SourceReport.source_event_id == report.source_event_id,
                SourceReport.earthquake_id.is_not(None),
                SourceReport.id != report.id,
            )
            .order_by(SourceReport.report_number.desc())
        )
        event = previous_link.earthquake if previous_link else self._find_candidate(session, report)
        if event is None:
            event = Earthquake(
                origin_time=report.origin_time,
                hypocenter=report.hypocenter,
                latitude=report.latitude,
                longitude=report.longitude,
                magnitude=report.magnitude,
                depth_km=report.depth_km,
                status=report.status,
                latest_source=report.source,
            )
            session.add(event)
            session.flush()
            report.earthquake_id = event.id
            snapshot = _snapshot(event)
            session.add(
                EventRevision(earthquake_id=event.id, revision=1, snapshot=snapshot, changes={})
            )
            return event, {}, True

        report.earthquake_id = event.id
        previous = _snapshot(event)
        current_priority = SOURCE_PRIORITY.get(event.latest_source, 0)
        incoming_priority = SOURCE_PRIORITY.get(report.source, 0)
        reviewed_is_sticky = event.status == EventStatus.reviewed and incoming_priority < 3
        if not reviewed_is_sticky and incoming_priority >= current_priority:
            event.origin_time = report.origin_time
            event.hypocenter = report.hypocenter
            event.latitude = report.latitude
            event.longitude = report.longitude
            event.magnitude = report.magnitude
            event.depth_km = report.depth_km
            event.status = report.status
            event.latest_source = report.source
        current = _snapshot(event)
        changes = _material_changes(previous, current)
        if current != previous:
            event.revision += 1
            event.updated_at = datetime.now(UTC)
            session.add(
                EventRevision(
                    earthquake_id=event.id,
                    revision=event.revision,
                    snapshot=current,
                    changes=changes,
                )
            )
        return event, changes, False

    @staticmethod
    def _find_candidate(session: Session, report: SourceReport) -> Earthquake | None:
        candidates = session.scalars(
            select(Earthquake).where(
                Earthquake.origin_time >= report.origin_time - timedelta(seconds=90),
                Earthquake.origin_time <= report.origin_time + timedelta(seconds=90),
            )
        ).all()
        scored: list[tuple[float, Earthquake]] = []
        for event in candidates:
            distance = haversine_km(
                event.latitude, event.longitude, report.latitude, report.longitude
            )
            mag_delta = (
                abs(event.magnitude - report.magnitude)
                if event.magnitude is not None and report.magnitude is not None
                else 0.5
            )
            if distance <= 50 and mag_delta <= 1.0:
                seconds = abs(
                    (_as_utc(event.origin_time) - _as_utc(report.origin_time)).total_seconds()
                )
                scored.append((seconds / 90 + distance / 50 + mag_delta, event))
        scored.sort(key=lambda item: item[0])
        if not scored or (len(scored) > 1 and scored[1][0] - scored[0][0] < 0.25):
            return None
        return scored[0][1]

    def _calculate_impacts(self, session: Session, event: Earthquake) -> None:
        already = session.scalar(
            select(ImpactEstimate.id).where(
                ImpactEstimate.earthquake_id == event.id,
                ImpactEstimate.revision == event.revision,
            )
        )
        if already:
            return
        locations = session.scalars(select(Location).where(Location.enabled.is_(True))).all()
        for location in locations:
            result = self._estimate(
                magnitude=event.magnitude,
                depth_km=event.depth_km,
                event_latitude=event.latitude,
                event_longitude=event.longitude,
                location_latitude=location.latitude,
                location_longitude=location.longitude,
            )
            session.add(
                ImpactEstimate(
                    earthquake_id=event.id,
                    revision=event.revision,
                    location_id=location.id,
                    location_name=location.name,
                    location_latitude=location.latitude,
                    location_longitude=location.longitude,
                    epicentral_distance_km=result.epicentral_distance_km,
                    hypocentral_distance_km=result.hypocentral_distance_km,
                    estimated_intensity=result.estimated_intensity,
                    intensity_level=result.intensity_level,
                    confidence=result.confidence,
                    model_version=result.model_version,
                    estimation_status=result.status,
                    estimation_error=result.error,
                    triggered=result.triggered,
                )
            )
        session.flush()

    def recalculate_location(self, session: Session, location: Location) -> None:
        events = session.scalars(select(Earthquake)).all()
        for event in events:
            existing = session.scalar(
                select(ImpactEstimate).where(
                    ImpactEstimate.location_id == location.id,
                    ImpactEstimate.earthquake_id == event.id,
                    ImpactEstimate.revision == event.revision,
                )
            )
            if existing:
                session.delete(existing)
                session.flush()
            result = self._estimate(
                magnitude=event.magnitude,
                depth_km=event.depth_km,
                event_latitude=event.latitude,
                event_longitude=event.longitude,
                location_latitude=location.latitude,
                location_longitude=location.longitude,
            )
            session.add(
                ImpactEstimate(
                    earthquake_id=event.id,
                    revision=event.revision,
                    location_id=location.id,
                    location_name=location.name,
                    location_latitude=location.latitude,
                    location_longitude=location.longitude,
                    epicentral_distance_km=result.epicentral_distance_km,
                    hypocentral_distance_km=result.hypocentral_distance_km,
                    estimated_intensity=result.estimated_intensity,
                    intensity_level=result.intensity_level,
                    confidence=result.confidence,
                    model_version=result.model_version,
                    estimation_status=result.status,
                    estimation_error=result.error,
                    triggered=result.triggered,
                )
            )

    @staticmethod
    def _append_impact_changes(
        session: Session, event: Earthquake, changes: dict[str, Any]
    ) -> None:
        if event.revision <= 1:
            return
        current = {
            row.location_id: row
            for row in session.scalars(
                select(ImpactEstimate).where(
                    ImpactEstimate.earthquake_id == event.id,
                    ImpactEstimate.revision == event.revision,
                )
            ).all()
        }
        previous = {
            row.location_id: row
            for row in session.scalars(
                select(ImpactEstimate).where(
                    ImpactEstimate.earthquake_id == event.id,
                    ImpactEstimate.revision == event.revision - 1,
                )
            ).all()
        }
        changed_levels: dict[str, Any] = {}
        affected_added: list[str] = []
        affected_removed: list[str] = []
        for location_id in current.keys() | previous.keys():
            now = current.get(location_id)
            before = previous.get(location_id)
            if now and before and now.intensity_level != before.intensity_level:
                changed_levels[location_id] = {
                    "from": before.intensity_level,
                    "to": now.intensity_level,
                }
            if now and now.triggered and (not before or not before.triggered):
                affected_added.append(location_id)
            if before and before.triggered and (not now or not now.triggered):
                affected_removed.append(location_id)
        if changed_levels:
            changes["estimated_intensity"] = changed_levels
        if affected_added:
            changes["affected_locations_added"] = affected_added
        if affected_removed:
            changes["affected_locations_removed"] = affected_removed

    @staticmethod
    def _queue_if_needed(
        session: Session,
        event: Earthquake,
        changes: dict[str, Any],
        is_new: bool,
    ) -> None:
        impacts = session.scalars(
            select(ImpactEstimate).where(
                ImpactEstimate.earthquake_id == event.id,
                ImpactEstimate.revision == event.revision,
                ImpactEstimate.triggered.is_(True),
            )
        ).all()
        was_queued = event.notified_revision is not None
        should_notify = (bool(impacts) and is_new) or (was_queued and bool(changes))
        if event.status == EventStatus.cancelled and was_queued:
            should_notify = True
        if not should_notify:
            return
        age = datetime.now(UTC) - _as_utc(event.origin_time)
        if age > timedelta(hours=24):
            return
        kind = "earthquake.initial" if not was_queued else "earthquake.update"
        if event.status == EventStatus.cancelled:
            kind = "earthquake.cancelled"
        enqueue_for_all_endpoints(
            session,
            event=event,
            kind=kind,
            changes=changes,
            delayed=age > timedelta(minutes=10),
        )
        event.notified_revision = event.revision


fusion_service = FusionService()
