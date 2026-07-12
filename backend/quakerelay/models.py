import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class EventStatus(enum.StrEnum):
    preliminary = "preliminary"
    reviewed = "reviewed"
    final = "final"
    cancelled = "cancelled"


class JobStatus(enum.StrEnum):
    pending = "pending"
    processing = "processing"
    delivered = "delivered"
    failed = "failed"


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    source: Mapped[str] = mapped_column(String(32), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    parse_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceReport(Base):
    __tablename__ = "source_reports"
    __table_args__ = (Index("ix_reports_origin_location", "origin_time", "latitude", "longitude"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    raw_message_id: Mapped[str] = mapped_column(ForeignKey("raw_messages.id"), index=True)
    earthquake_id: Mapped[str | None] = mapped_column(ForeignKey("earthquakes.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_event_id: Mapped[str] = mapped_column(String(128), index=True)
    report_number: Mapped[int] = mapped_column(Integer, default=1)
    report_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    origin_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hypocenter: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    magnitude: Mapped[float | None] = mapped_column(Float)
    depth_km: Mapped[float | None] = mapped_column(Float)
    max_intensity: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.preliminary)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    raw_message: Mapped[RawMessage] = relationship()
    earthquake: Mapped["Earthquake | None"] = relationship(back_populates="reports")


class Earthquake(Base):
    __tablename__ = "earthquakes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    origin_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hypocenter: Mapped[str] = mapped_column(String(255), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    magnitude: Mapped[float | None] = mapped_column(Float, index=True)
    depth_km: Mapped[float | None] = mapped_column(Float)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.preliminary)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    latest_source: Mapped[str] = mapped_column(String(32))
    notified_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    reports: Mapped[list[SourceReport]] = relationship(back_populates="earthquake")
    revisions: Mapped[list["EventRevision"]] = relationship(back_populates="earthquake")
    impacts: Mapped[list["ImpactEstimate"]] = relationship(back_populates="earthquake")


class EventRevision(Base):
    __tablename__ = "event_revisions"
    __table_args__ = (UniqueConstraint("earthquake_id", "revision", name="uq_event_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    earthquake_id: Mapped[str] = mapped_column(ForeignKey("earthquakes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    earthquake: Mapped[Earthquake] = relationship(back_populates="revisions")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(255), default="")
    province: Mapped[str] = mapped_column(String(100), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    district: Mapped[str] = mapped_column(String(100), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ImpactEstimate(Base):
    __tablename__ = "impact_estimates"
    __table_args__ = (
        UniqueConstraint("earthquake_id", "revision", "location_id", name="uq_impact_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    earthquake_id: Mapped[str] = mapped_column(ForeignKey("earthquakes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    location_name: Mapped[str] = mapped_column(String(100))
    location_latitude: Mapped[float] = mapped_column(Float)
    location_longitude: Mapped[float] = mapped_column(Float)
    epicentral_distance_km: Mapped[float] = mapped_column(Float)
    hypocentral_distance_km: Mapped[float] = mapped_column(Float)
    estimated_intensity: Mapped[float | None] = mapped_column(Float)
    intensity_level: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(16))
    model_version: Mapped[str] = mapped_column(String(64))
    estimation_status: Mapped[str] = mapped_column(String(32), default="estimated")
    estimation_error: Mapped[str | None] = mapped_column(String(500))
    triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    earthquake: Mapped[Earthquake] = relationship(back_populates="impacts")
    location: Mapped[Location] = relationship()


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(100))
    channel_type: Mapped[str] = mapped_column(String(32), default="generic")
    url: Mapped[str] = mapped_column(Text)
    encrypted_headers: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    encrypted_config: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    earthquake_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weather_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "idempotency_key", name="uq_job_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id"), index=True)
    earthquake_id: Mapped[str | None] = mapped_column(ForeignKey("earthquakes.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.pending, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    endpoint: Mapped[WebhookEndpoint] = relationship()
    deliveries: Mapped[list["DeliveryAttempt"]] = relationship(back_populates="job")


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    job_id: Mapped[str] = mapped_column(ForeignKey("notification_jobs.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_excerpt: Mapped[str | None] = mapped_column(String(1000))
    error: Mapped[str | None] = mapped_column(String(1000))

    job: Mapped[NotificationJob] = relationship(back_populates="deliveries")


class SourceHealth(Base):
    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    latest_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    outage_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    hour_key: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    temperature_rank: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rain_rank: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    wind_rank: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
