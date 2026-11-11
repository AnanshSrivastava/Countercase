import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.router import router as agent_router
from app.core.errors import install_error_handlers
from app.core.router import router as core_router
from app.settings import settings

log = logging.getLogger(__name__)


async def _alert_loop(interval: int) -> None:
    from fastapi.concurrency import run_in_threadpool

    from app.core.alerts import run_alerts
    from app.core.db import session_factory

    def once() -> int:
        with session_factory()() as session:
            return len(run_alerts(session))

    while True:
        try:
            sent = await run_in_threadpool(once)
            if sent:
                log.info("deadline alerts: %d sent", sent)
        except Exception:  # noqa: BLE001 - the checker must never take the API down
            log.exception("deadline alert check failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = None
    if settings.alerts_interval_seconds > 0:
        task = asyncio.create_task(_alert_loop(settings.alerts_interval_seconds))
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Countercase API", version="0.1.0", lifespan=lifespan)
install_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(core_router, prefix="/core", tags=["core"])
app.include_router(agent_router, prefix="/agent", tags=["agent"])
