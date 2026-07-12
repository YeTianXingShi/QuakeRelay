from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUAKERELAY_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/quakerelay.db"
    secret_key: str = Field(default_factory=lambda: Fernet.generate_key().decode())
    amap_js_key: str = ""
    amap_security_code: str = ""
    log_level: str = "INFO"
    enable_collector: bool = True
    public_base_url: str = "http://localhost:8080"
    data_dir: Path = Path("/data")
    recovery_window_hours: int = 24
    source_down_minutes: int = 10

    @field_validator("secret_key")
    @classmethod
    def valid_fernet_key(cls, value: str) -> str:
        try:
            Fernet(value.encode())
        except ValueError as exc:
            raise ValueError("secret_key must be a valid Fernet key") from exc
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
