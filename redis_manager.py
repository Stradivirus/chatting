import aioredis
import os
import json
import asyncio

class RedisManager:
    def __init__(self):
        self.redis_hosts = os.getenv("REDIS_HOSTS", "redis-cluster-0.redis-cluster.chat.svc.cluster.local:6379,redis-cluster-1.redis-cluster.chat.svc.cluster.local:6379,redis-cluster-2.redis-cluster.chat.svc.cluster.local:6379,redis-cluster-3.redis-cluster.chat.svc.cluster.local:6379,redis-cluster-4.redis-cluster.chat.svc.cluster.local:6379,redis-cluster-5.redis-cluster.chat.svc.cluster.local:6379").split(',')
        self.redis = None
        self.pubsub = None

    async def connect(self):
        if not self.redis:
            try:
                self.redis = await aioredis.RedisCluster.from_url(f"redis://{self.redis_hosts[0]}", startup_nodes=self.redis_hosts)
                self.pubsub = self.redis.pubsub()
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")
                raise

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
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message is not None:
                    yield json.loads(message['data'])
            except Exception as e:
                print(f"Error while listening: {e}")
                await asyncio.sleep(1)  # 오류 발생 시 잠시 대기

    async def close(self):
        if self.redis:
            await self.redis.close()