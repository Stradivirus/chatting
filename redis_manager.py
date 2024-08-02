import aioredis
import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis_service = os.getenv("REDIS_SERVICE", "redis-service")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_replicas = int(os.getenv("REDIS_REPLICAS", 3))
        self.redis = None
        self.pubsub = None

    async def connect(self, max_retries=5, retry_delay=5):
        for attempt in range(max_retries):
            try:
                if not self.redis:
                    for i in range(self.redis_replicas):
                        try:
                            redis_host = f"{self.redis_service}-{i}.{self.redis_service}"
                            redis_url = f"redis://{redis_host}:{self.redis_port}"
                            self.redis = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                            self.pubsub = self.redis.pubsub()
                            logger.info(f"Successfully connected to Redis at {redis_url}")
                            return
                        except aioredis.RedisError as e:
                            logger.warning(f"Failed to connect to Redis at {redis_url}: {str(e)}")
                    raise Exception("Failed to connect to any Redis replica")
            except Exception as e:
                logger.error(f"Failed to connect to Redis (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        raise Exception("Failed to connect to Redis after multiple attempts")

    async def publish(self, channel, message):
        try:
            if not self.redis:
                await self.connect()
            await self.redis.publish(channel, message)
        except Exception as e:
            logger.error(f"Error publishing message: {str(e)}")
            raise

    async def subscribe(self, channel):
        try:
            if not self.pubsub:
                await self.connect()
            await self.pubsub.subscribe(channel)
        except Exception as e:
            logger.error(f"Error subscribing to channel: {str(e)}")
            raise

    async def listen(self):
        if not self.pubsub:
            raise Exception("Not subscribed to any channel")
        while True:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message is not None:
                    yield json.loads(message['data'])
            except Exception as e:
                logger.error(f"Error while listening for messages: {str(e)}")
                await asyncio.sleep(1)  # 오류 발생 시 잠시 대기

    async def close(self):
        if self.redis:
            await self.redis.close()
            logger.info("Closed Redis connection")