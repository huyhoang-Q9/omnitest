"""Gửi job sang worker qua Dramatiq (Redis). API không import code worker, chỉ gửi message theo tên actor."""

import uuid

from omnitest_api.config import get_settings

RUNS_QUEUE = "runs"
EXECUTE_RUN_ACTOR = "execute_run"


def enqueue_run(run_id: uuid.UUID) -> None:
    settings = get_settings()
    if settings.queue_backend == "none":
        return
    from dramatiq import Message
    from dramatiq.brokers.redis import RedisBroker

    broker = RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]
    try:
        broker.enqueue(
            Message(
                queue_name=RUNS_QUEUE,
                actor_name=EXECUTE_RUN_ACTOR,
                args=(str(run_id),),
                kwargs={},
                options={},
            )
        )
    finally:
        broker.close()
