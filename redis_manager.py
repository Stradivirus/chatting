import aioredis
import os
import json
import asyncio

class RedisManager:
    def __init__(self):
        self.redis_hosts = os.getenv("REDIS_HOSTS", "redis-cluster-0.redis-cluster.chat.svc.cluster.local,redis-cluster-1.redis-cluster.chat.svc.cluster.local,redis-cluster-2.redis-cluster.chat.svc.cluster.local,redis-cluster-3.redis-cluster.chat.svc.cluster.local,redis-cluster-4.redis-cluster.chat.svc.cluster.local,redis-cluster-5.redis-cluster.chat.svc.cluster.local").split(',')
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None
        self.pubsub = None

    async def connect(self):
        if not self.redis:
            startup_nodes = [{"host": host, "port": self.redis_port} for host in self.redis_hosts]
            self.redis = await aioredis.RedisCluster(startup_nodes=startup_nodes, decode_responses=True)
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