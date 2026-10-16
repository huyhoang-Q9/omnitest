"""Khai báo Dramatiq broker và actor. Chạy worker: dramatiq omnitest_worker.actors --processes 1 --threads 2"""

import asyncio
import logging
import uuid

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from sqlalchemy.ext.asyncio import create_async_engine

from omnitest_api.config import get_settings
from omnitest_api.queue import EXECUTE_RUN_ACTOR, RUNS_QUEUE
from omnitest_api.security.redaction import RedactingFilter
from omnitest_worker.executor import RunExecutor, run_once

logging.getLogger("omnitest").addFilter(RedactingFilter())
log = logging.getLogger("omnitest.worker")

broker = RedisBroker(url=get_settings().redis_url)  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)


async def _recover() -> int:
    engine = create_async_engine(get_settings().database_url)
    try:
        return await RunExecutor(engine).recover_stale_runs()
    finally:
        await engine.dispose()


try:
    recovered = asyncio.run(_recover())
    if recovered:
        log.warning("Đã đánh dấu lỗi %d lần chạy mất heartbeat", recovered)
except Exception:
    log.exception("Không kiểm tra được run treo khi khởi động worker")


# max_retries=0: việc thử lại do executor quyết định theo chính sách an toàn của từng test case.
@dramatiq.actor(
    actor_name=EXECUTE_RUN_ACTOR,
    queue_name=RUNS_QUEUE,
    max_retries=0,
    time_limit=6 * 60 * 60 * 1000,
)
def execute_run(run_id: str) -> None:
    status = asyncio.run(run_once(uuid.UUID(run_id)))
    log.info("Run %s kết thúc: %s", run_id, status)
