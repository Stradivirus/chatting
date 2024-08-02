import aioredis
import os
import json
import asyncio

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-service")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None
        self.pubsub = None

    async def connect(self):
        if not self.redis:
            redis_url = f"redis://{self.redis_host}:{self.redis_port}"
            self.redis = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            self.pubsub = self.redis.pubsub()

    async def publish(self, channel, message):
        if not self.redis:
            await self.connect()
        await self.redis.publish(channel, message)

    async def subscribe(self, channel):
        if not self.pubsub:
            await self.connect()
        await self.pubsub.subscribe(channel)

    async def listen(self):
        if not self.pubsub:
            raise Exception("Not subscribed to any channel")
        while True:
            message = await self.pubsub.get_message(ignore_subscribe_messages=True)
            if message is not None:
                yield json.loads(message['data'])

    async def close(self):
        if self.redis:
            await self.redis.close()