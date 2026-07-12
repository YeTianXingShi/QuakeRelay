import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .backup import BackupWorker
from .collector import WolfxCollector
from .config import get_settings
from .db import init_db
from .notifications import NotificationWorker


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    init_db()
    worker = NotificationWorker()
    backup_worker = BackupWorker()
    tasks = [
        asyncio.create_task(worker.run(), name="notification-worker"),
        asyncio.create_task(backup_worker.run(), name="backup-worker"),
    ]
    collector: WolfxCollector | None = None
    if settings.enable_collector:
        collector = WolfxCollector()
        tasks.append(asyncio.create_task(collector.run(), name="wolfx-collector"))
    yield
    worker.stop()
    backup_worker.stop()
    if collector:
        collector.stop()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title="QuakeRelay",
    version="0.1.0",
    description="个人自部署的地震信息查看与 Webhook 提醒服务",
    lifespan=lifespan,
)
app.include_router(router)

frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    assets = frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        candidate = frontend_dist / path
        if path and candidate.is_file() and frontend_dist in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")
