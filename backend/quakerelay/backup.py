import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings


def create_sqlite_backup() -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        raise ValueError("Only SQLite backup is supported")
    source_path = Path(settings.database_url.removeprefix("sqlite:///"))
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"quakerelay-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return {"filename": destination.name, "size": destination.stat().st_size}


def prune_backups(keep: int = 30) -> None:
    backup_dir = get_settings().data_dir / "backups"
    backups = sorted(backup_dir.glob("quakerelay-*.db"), reverse=True)
    for backup in backups[keep:]:
        backup.unlink(missing_ok=True)


class BackupWorker:
    def __init__(self) -> None:
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=24 * 60 * 60)
            except TimeoutError:
                await asyncio.to_thread(create_sqlite_backup)
                await asyncio.to_thread(prune_backups)

    def stop(self) -> None:
        self._stop.set()
