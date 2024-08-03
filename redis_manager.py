import os
import json
import asyncio
import ipaddress
from redis.asyncio import Redis

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None
        self.pubsub = None
        self.max_connections_per_ip = 3
        self.connection_timeout = 3600  # 1 hour

    async def connect(self):
        if not self.redis:
            try:
                self.redis = Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
                await self.redis.ping()
                self.pubsub = self.redis.pubsub()
                print(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
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
                await asyncio.sleep(1)

    async def close(self):
        if self.redis:
            await self.redis.close()

    async def is_vpn_or_proxy(self, ip_address):
        # This is a simplified check. In a real-world scenario, you'd want to use a more
        # comprehensive database or API to check for VPNs and proxies.
        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback or ip.is_reserved
        except ValueError:
            return True

    async def can_connect(self, ip_address):
        if await self.is_vpn_or_proxy(ip_address):
            return False

        key = f"ip:{ip_address}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.connection_timeout)
        result = await pipe.execute()
        
        connection_count = result[0]
        return connection_count <= self.max_connections_per_ip

    async def remove_connection(self, ip_address):
        key = f"ip:{ip_address}"
        await self.redis.decr(key)