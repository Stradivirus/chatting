import os
import json
import asyncio
import ipaddress
from redis.asyncio import RedisCluster
from redis.exceptions import RedisError
import aiohttp
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None
        self.pubsub = None
        self.blocked_ips = set()
        self.connection_counts = {}
        self.max_connections_per_ip = 3
        self.chat_list_key = "chat_messages"
        self.message_ttl = 7200  # 2 hours in seconds

    async def connect(self):
        if not self.redis:
            try:
                self.redis = await RedisCluster.from_url(
                    f"redis://{self.redis_host}:{self.redis_port}",
                    decode_responses=True
                )
                await self.redis.ping()
                logger.info(f"Connected to Redis Cluster at {self.redis_host}:{self.redis_port}")
            except RedisError as e:
                logger.error(f"Failed to connect to Redis Cluster: {e}")
                raise

    async def reconnect(self, max_retries=3):
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(2 ** attempt)
                await self.connect()
                return
            except RedisError as e:
                logger.error(f"Reconnection attempt {attempt + 1} failed: {e}")
        raise Exception("Failed to reconnect to Redis Cluster after multiple attempts")

    async def save_message(self, message):
        try:
            if not self.redis:
                await self.connect()
            
            message_str = json.dumps(message)
            
            # 파이프라인을 사용하여 여러 작업을 한 번에 실행
            async with self.redis.pipeline(transaction=False) as pipe:
                await pipe.zadd(self.chat_list_key, {message_str: message['timestamp']})
                await pipe.expire(self.chat_list_key, self.message_ttl)
                await pipe.publish("chat", message_str)
                await pipe.execute()
            
            logger.info(f"Message saved: {message['id']}")
        except RedisError as e:
            logger.error(f"Error saving message: {e}")
            await self.reconnect()

    async def get_messages(self, count=100):
        try:
            if not self.redis:
                await self.connect()
            
            current_time = datetime.now().timestamp()
            two_hours_ago = (datetime.now() - timedelta(hours=2)).timestamp()

            messages = await self.redis.zrevrangebyscore(self.chat_list_key, current_time, two_hours_ago, start=0, num=count)
            return [json.loads(msg) for msg in messages]
        except RedisError as e:
            logger.error(f"Error retrieving messages: {e}")
            await self.reconnect()
            return []

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
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(channel)
        except RedisError as e:
            logger.error(f"Error subscribing to channel: {e}")
            await self.reconnect()
            self.pubsub = self.redis.pubsub()
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
                logger.error(f"Error while listening: {e}")
                await self.reconnect()
            except Exception as e:
                logger.error(f"Unexpected error while listening: {e}")
                await asyncio.sleep(1)

    async def close(self):
        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()

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

    def increment_connection_count(self, ip_address):
        if not ipaddress.ip_address(ip_address).is_private:
            self.connection_counts[ip_address] = self.connection_counts.get(ip_address, 0) + 1

    def decrement_connection_count(self, ip_address):
        if not ipaddress.ip_address(ip_address).is_private:
            if ip_address in self.connection_counts:
                self.connection_counts[ip_address] -= 1
                if self.connection_counts[ip_address] <= 0:
                    del self.connection_counts[ip_address]