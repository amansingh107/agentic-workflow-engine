import json
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
import redis.asyncio as aioredis
from ..config import settings

logger = logging.getLogger(__name__)


class EventBus:
    """
    Asynchronous event bus supporting Redis Pub/Sub with
    in-memory asyncio.Queue fallback for local development.
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._local_queues: Dict[str, list[asyncio.Queue]] = {}
        self._redis_available: Optional[bool] = None

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        if self._redis_available is False:
            return None
        if self._redis is None:
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    socket_connect_timeout=1.0,
                    decode_responses=True,
                )
                await client.ping()
                self._redis = client
                self._redis_available = True
                logger.info("Connected to Redis for live event streaming.")
            except Exception as e:
                self._redis_available = False
                self._redis = None
                logger.warning(f"Redis is unavailable ({e}). Falling back to in-memory event queues.")
        return self._redis

    async def publish_event(self, thread_id: str, event_type: str, data: Dict[str, Any]):
        """Publishes an event to both Redis and local in-memory subscribers."""
        payload = {
            "thread_id": thread_id,
            "type": event_type,
            "data": data,
        }
        msg_str = json.dumps(payload)

        # 1. Try Redis Pub/Sub
        redis_client = await self._get_redis()
        if redis_client:
            try:
                await redis_client.publish(f"workflow:{thread_id}", msg_str)
            except Exception as e:
                logger.error(f"Failed to publish to Redis: {e}")

        # 2. Local in-memory fan-out
        if thread_id in self._local_queues:
            for q in self._local_queues[thread_id]:
                await q.put(payload)

    async def subscribe_events(self, thread_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribes to events for a specific thread_id."""
        redis_client = await self._get_redis()
        
        # Redis Pub/Sub subscription
        if redis_client:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(f"workflow:{thread_id}")
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        yield json.loads(message["data"])
            finally:
                await pubsub.unsubscribe(f"workflow:{thread_id}")
                await pubsub.close()
        else:
            # In-memory queue subscription
            queue = asyncio.Queue()
            if thread_id not in self._local_queues:
                self._local_queues[thread_id] = []
            self._local_queues[thread_id].append(queue)
            try:
                while True:
                    event = await queue.get()
                    yield event
                    if event.get("type") in ["completed", "failed", "rejected_by_human"]:
                        break
            finally:
                if thread_id in self._local_queues and queue in self._local_queues[thread_id]:
                    self._local_queues[thread_id].remove(queue)


event_bus = EventBus()
