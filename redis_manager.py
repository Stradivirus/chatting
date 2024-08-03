import os
import json
import asyncio
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.pool = None
        self.pubsub = None

    async def connect(self):
        if not self.pool:
            try:
                self.pool = ConnectionPool(
                    host=self.redis_host,
                    port=self.redis_port,
                    decode_responses=True,
                    max_connections=10
                )
                self.redis = Redis(connection_pool=self.pool)
                await self.redis.ping()
                self.pubsub = self.redis.pubsub()
                print(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            except RedisError as e:
                print(f"Failed to connect to Redis: {e}")
                await self.reconnect()

    async def reconnect(self, max_retries=3):
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                await self.connect()
                return
            except RedisError as e:
                print(f"Reconnection attempt {attempt + 1} failed: {e}")
        raise Exception("Failed to reconnect to Redis after multiple attempts")

    async def publish(self, channel, message):
        try:
            if not self.pool:
                await self.connect()
            return await self.redis.publish(channel, message)
        except RedisError as e:
            print(f"Error publishing message: {e}")
            await self.reconnect()
            return await self.redis.publish(channel, message)

    async def subscribe(self, channel):
        try:
            if not self.pubsub:
                await self.connect()
            await self.pubsub.subscribe(channel)
        except RedisError as e:
            print(f"Error subscribing to channel: {e}")
            await self.reconnect()
            await self.pubsub.subscribe(channel)

    async def listen(self):
        if not self.pubsub:
            raise Exception("Not subscribed to any channel")
        while True:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True)
                if message is not None:
                    yield json.loads(message['data'])
            except RedisError as e:
                print(f"Error while listening: {e}")
                await self.reconnect()
            except Exception as e:
                print(f"Unexpected error while listening: {e}")
                await asyncio.sleep(1)

    async def close(self):
        if self.pool:
            await self.pool.disconnect()

    async def check_ip(self, ip_address):
        if ip_address in self.blocked_ips:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://vpn-proxy-detection.com/api/check/{ip_address}') as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('is_vpn') or data.get('is_proxy'):
                            self.blocked_ips.add(ip_address)
                            return False
        except Exception as e:
            print(f"Error checking IP {ip_address}: {e}")

        return True

    async def is_allowed_connection(self, ip_address):
        if not ipaddress.ip_address(ip_address).is_global:
            return False
        return await self.check_ip(ip_address)