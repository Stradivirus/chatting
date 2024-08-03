import os
import json
import asyncio
import ipaddress
import socket
from redis.asyncio import Redis

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.fastapi_service = os.getenv("FASTAPI_SERVICE", "fastapi-service.chat.svc.cluster.local")
        self.redis = None
        self.pubsub = None
        self.max_connections_per_ip = 3
        self.connection_timeout = 3600  # 1 hour
        self.whitelist = set()

    async def connect(self):
        if not self.redis:
            try:
                self.redis = Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
                await self.redis.ping()
                self.pubsub = self.redis.pubsub()
                print(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
                
                # FastAPI 서비스 IP 주소들을 화이트리스트에 추가
                fastapi_ips = await self.get_service_ips(self.fastapi_service)
                for ip in fastapi_ips:
                    await self.add_to_whitelist(ip)
                print(f"Added FastAPI service IPs to whitelist: {fastapi_ips}")
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")
                raise

    async def get_service_ips(self, service_name):
        try:
            ips = socket.gethostbyname_ex(service_name)[2]
            return ips
        except socket.gaierror:
            print(f"Unable to resolve {service_name}")
            return []

    async def add_to_whitelist(self, ip_address):
        self.whitelist.add(ip_address)

    async def is_whitelisted(self, ip_address):
        return ip_address in self.whitelist

    async def is_vpn_or_proxy(self, ip_address):
        if await self.is_whitelisted(ip_address):
            return False
        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback or ip.is_reserved
        except ValueError:
            return True

    async def can_connect(self, ip_address):
        if await self.is_whitelisted(ip_address):
            return True

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
        if not await self.is_whitelisted(ip_address):
            key = f"ip:{ip_address}"
            await self.redis.decr(key)

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