import os
import json
import asyncio
import ipaddress
from redis.asyncio import RedisCluster
from redis.exceptions import RedisError
import aiohttp
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis_hosts = os.getenv("REDIS_HOSTS", "redis-cluster.chat.svc.cluster.local:6379").split(",")
        self.redis = None
        self.blocked_ips = set()
        self.connection_counts = {}
        self.max_connections_per_ip = 3
        self.active_users_key = "active_users"  # 새로 추가: 활성 사용자를 저장할 키

    async def connect(self):
        if not self.redis:
            try:
                self.redis = await RedisCluster.from_url(f"redis://{self.redis_hosts[0]}", decode_responses=True)
                await self.redis.ping()
                logger.info(f"Connected to Redis Cluster at {self.redis_hosts}")
            except RedisError as e:
                logger.error(f"Failed to connect to Redis Cluster: {e}")
                await self.reconnect()

    async def reconnect(self, max_retries=3):
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(2 ** attempt)
                await self.connect()
                return
            except RedisError as e:
                logger.error(f"Reconnection attempt {attempt + 1} failed: {e}")
        raise Exception("Failed to reconnect to Redis Cluster after multiple attempts")

    async def publish(self, channel, message):
        try:
            if not self.redis:
                await self.connect()
            return await self.redis.publish(channel, message)
        except RedisError as e:
            logger.error(f"Error publishing message: {e}")
            await self.reconnect()
            return await self.redis.publish(channel, message)

    async def subscribe(self, channel):
        try:
            if not self.redis:
                await self.connect()
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except RedisError as e:
            logger.error(f"Error subscribing to channel: {e}")
            await self.reconnect()
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(channel)
            return pubsub

    async def listen(self):
        pubsub = await self.subscribe("chat")
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message is not None:
                    yield json.loads(message['data'])
            except RedisError as e:
                logger.error(f"Error while listening: {e}")
                await self.reconnect()
                pubsub = await self.subscribe("chat")
            except Exception as e:
                logger.error(f"Unexpected error while listening: {e}")
                await asyncio.sleep(1)

    async def close(self):
        if self.redis:
            await self.redis.close()

    async def check_ip(self, ip_address):
        if ip_address in self.blocked_ips:
            logger.info(f"IP {ip_address} is in blocked list")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://vpn-proxy-detection.com/api/check/{ip_address}') as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('is_vpn') or data.get('is_proxy'):
                            logger.warning(f"IP {ip_address} detected as VPN/Proxy")
                            self.blocked_ips.add(ip_address)
                            return False
                        else:
                            logger.info(f"IP {ip_address} is not a VPN/Proxy")
                    else:
                        logger.error(f"Error response from VPN/Proxy detection service: {response.status}")
        except Exception as e:
            logger.error(f"Error checking IP {ip_address}: {e}")
        
        return True

    async def is_allowed_connection(self, ip_address):
        try:
            ip = ipaddress.ip_address(ip_address)
            
            if ip.is_private:
                logger.info(f"IP {ip_address} is private, allowing connection without restrictions")
                return True
            
            if ip.is_global:
                if self.connection_counts.get(ip_address, 0) >= self.max_connections_per_ip:
                    logger.warning(f"IP {ip_address} has reached the maximum number of connections")
                    return False
                
                logger.info(f"IP {ip_address} is global, checking for VPN/Proxy")
                if not await self.check_ip(ip_address):
                    return False
                
                return True
            
            logger.warning(f"IP {ip_address} is not private or global, blocking connection")
            return False

        except ValueError:
            logger.error(f"Invalid IP address: {ip_address}")
            return False

    def increment_connection_count(self, ip_address):
        if not ipaddress.ip_address(ip_address).is_private:
            self.connection_counts[ip_address] = self.connection_counts.get(ip_address, 0) + 1

    def decrement_connection_count(self, ip_address):
        if not ipaddress.ip_address(ip_address).is_private:
            if ip_address in self.connection_counts:
                self.connection_counts[ip_address] -= 1
                if self.connection_counts[ip_address] <= 0:
                    del self.connection_counts[ip_address]

    # 새로 추가: 활성 사용자 추가
    async def add_active_user(self, client_id):
        try:
            await self.redis.sadd(self.active_users_key, client_id)
            count = await self.get_active_users_count()
            await self.publish_active_users(count)
        except RedisError as e:
            logger.error(f"Error adding active user: {e}")
            await self.reconnect()

    # 새로 추가: 활성 사용자 제거
    async def remove_active_user(self, client_id):
        try:
            await self.redis.srem(self.active_users_key, client_id)
            count = await self.get_active_users_count()
            await self.publish_active_users(count)
        except RedisError as e:
            logger.error(f"Error removing active user: {e}")
            await self.reconnect()

    # 새로 추가: 활성 사용자 수 조회
    async def get_active_users_count(self):
        try:
            return await self.redis.scard(self.active_users_key)
        except RedisError as e:
            logger.error(f"Error getting active users count: {e}")
            await self.reconnect()
            return 0

    # 새로 추가: 활성 사용자 수 발행
    async def publish_active_users(self, count):
        message = {
            "type": "active_users",
            "count": count
        }
        await self.publish("active_users", json.dumps(message))