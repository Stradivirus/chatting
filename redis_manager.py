import aioredis
import os

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-service")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None

    async def connect(self):
        if not self.redis:
            redis_url = f"redis://{self.redis_host}:{self.redis_port}"
            self.redis = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def publish(self, channel, message):
        if not self.redis:
            await self.connect()
        await self.redis.publish(channel, message)

    async def subscribe(self, channel):
        if not self.redis:
            await self.connect()
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

    async def close(self):
        if self.redis:
            await self.redis.close()