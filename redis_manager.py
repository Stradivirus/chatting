import aioredis
import os

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-service")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None

    async def connect(self):
        if not self.redis:
            self.redis = await aioredis.create_redis_pool(f"redis://{self.redis_host}:{self.redis_port}")

    async def publish(self, channel, message):
        await self.connect()
        await self.redis.publish(channel, message)

    async def close(self):
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()