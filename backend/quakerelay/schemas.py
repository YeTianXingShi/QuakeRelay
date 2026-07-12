from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(default="", max_length=255)
    province: str = Field(min_length=1, max_length=100)
    city: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    coordinate_system: Literal["gcj02", "wgs84"] = "gcj02"
    enabled: bool = True

    @model_validator(mode="after")
    def require_city_or_district(self) -> "LocationCreate":
        if not self.city.strip() and not self.district.strip():
            raise ValueError("city or district is required")
        return self


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinate_system: Literal["gcj02", "wgs84"] = "gcj02"
    enabled: bool | None = None


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    enabled: bool = True
    earthquake_enabled: bool = True
    weather_enabled: bool = False


class WebhookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: HttpUrl | None = None
    headers: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None
    earthquake_enabled: bool | None = None
    weather_enabled: bool | None = None


class TelegramCreate(BaseModel):
    name: str = Field(default="Telegram", min_length=1, max_length=100)
    bot_token: str = Field(pattern=r"^\d+:[A-Za-z0-9_-]{20,}$")
    chat_id: str = Field(min_length=1, max_length=100)
    message_thread_id: int | None = Field(default=None, ge=1)
    disable_notification: bool = False
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    enabled: bool = True
    earthquake_enabled: bool = True
    weather_enabled: bool = False


class IngestDebugRequest(BaseModel):
    payload: dict[str, Any]
    source: str | None = None
