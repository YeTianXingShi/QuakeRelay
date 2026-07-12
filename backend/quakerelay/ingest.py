import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .fusion import fusion_service
from .models import RawMessage


def ingest_payload(
    session: Session, payload: dict[str, Any], source_hint: str | None = None
) -> list[str]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    canonical = f"{source_hint or ''}:{canonical}"
    content_hash = hashlib.sha256(canonical.encode()).hexdigest()
    existing = session.scalar(select(RawMessage).where(RawMessage.content_hash == content_hash))
    if existing:
        return []
    source = str(payload.get("type") or source_hint or "unknown")
    raw = RawMessage(source=source, content_hash=content_hash, payload=payload)
    session.add(raw)
    session.flush()
    events = fusion_service.process_raw(session, raw)
    return [event.id for event in events]
