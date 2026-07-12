import json
from typing import Any

from cryptography.fernet import Fernet

from .config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().secret_key.encode())


def encrypt_json(value: dict[str, Any]) -> bytes:
    return _fernet().encrypt(json.dumps(value, ensure_ascii=False).encode())


def decrypt_json(value: bytes) -> dict[str, Any]:
    if not value:
        return {}
    result = json.loads(_fernet().decrypt(value).decode())
    return result if isinstance(result, dict) else {}
