import os
import json
import asyncio
import ipaddress
from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError
import aiohttp
import logging
import time

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.is_cluster = os.getenv("REDIS_CLUSTER", "false").lower() == "true"
        self.pool = None
        self.redis = None
        self.pubsub = None
        self.blocked_ips = set()
        self.connection_counts = {}
        self.max_connections_per_ip = 3
        self.chat_history_key = "chat_history"
        self.chat_history_ttl = 7200

    async def connect(self):
        if not self.redis:
            try:
                if self.is_cluster:
                    self.redis = RedisCluster(host=self.redis_host, port=self.redis_port, decode_responses=True)
                else:
                    self.pool = ConnectionPool(
                        host=self.redis_host,
                        port=self.redis_port,
                        decode_responses=True,
                        max_connections=20  # 연결 풀 크기 증가
                    )
                    self.redis = Redis(connection_pool=self.pool)
                
                await self.redis.ping()
                self.pubsub = self.redis.pubsub()
                logger.info(f"Connected to Redis{'Cluster' if self.is_cluster else ''} at {self.redis_host}:{self.redis_port}")
            except RedisError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                await self.reconnect()

    async def reconnect(self, max_retries=3):
        # Redis 재연결 시도
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(2 ** attempt)  # 지수 백오프
                await self.connect()
                return
            except RedisError as e:
                logger.error(f"Reconnection attempt {attempt + 1} failed: {e}")
        raise Exception("Failed to reconnect to Redis after multiple attempts")

    async def publish(self, channel, message):
        try:
            if not self.redis:
                await self.connect()
            await asyncio.gather(
                self.redis.publish(channel, message),
                self.add_to_chat_history(message)
            )
            return True
        except RedisError as e:
            logger.error(f"Error publishing message: {e}")
            await self.reconnect()
            return False

    async def add_to_chat_history(self, message):
        try:
            timestamp = time.time()
            await self.redis.zadd(self.chat_history_key, {message: timestamp})
            # 2시간이 지난 메시지 삭제
            await self.redis.zremrangebyscore(self.chat_history_key, 0, timestamp - self.chat_history_ttl)
            logger.debug(f"Added message to chat history and removed old messages: {message}")
        except RedisError as e:
            logger.error(f"Error adding message to chat history: {e}")

    async def get_chat_history(self):
        try:
            # 최근 2시간 동안의 채팅 기록만 반환
            current_time = time.time()
            return await self.redis.zrangebyscore(
                self.chat_history_key,
                current_time - self.chat_history_ttl,
                current_time
            )
        except RedisError as e:
            logger.error(f"Error retrieving chat history: {e}")
            return []

    async def get_chat_history(self):
        # 채팅 기록 조회
        try:
            return await self.redis.zrange(self.chat_history_key, 0, -1)
        except RedisError as e:
            logger.error(f"Error retrieving chat history: {e}")
            return []

    async def subscribe(self, channel):
        # 채널 구독
        try:
            if not self.pubsub:
                await self.connect()
            await self.pubsub.subscribe(channel)
        except RedisError as e:
            logger.error(f"Error subscribing to channel: {e}")
            await self.reconnect()
            await self.pubsub.subscribe(channel)

    async def listen(self):
        # 메시지 수신
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
        # Redis 연결 종료
        if self.pool:
            await self.pool.disconnect()

    async def check_ip(self, ip_address):
        # IP 주소가 VPN/프록시인지 확인
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
                return True
            
            if ip.is_global:
                if self.connection_counts.get(ip_address, 0) >= self.max_connections_per_ip:
                    logger.warning(f"IP {ip_address} has reached the maximum number of connections")
                    return False
                
                return await self.check_ip(ip_address)
            
            logger.warning(f"IP {ip_address} is not private or global, blocking connection")
            return False

        except ValueError:
            logger.error(f"Invalid IP address: {ip_address}")
            return False

        except ValueError:
            logger.error(f"Invalid IP address: {ip_address}")
            return False

    def increment_connection_count(self, ip_address):
        # 공인 IP 주소의 연결 수만 증가
        if not ipaddress.ip_address(ip_address).is_private:
            self.connection_counts[ip_address] = self.connection_counts.get(ip_address, 0) + 1

    def decrement_connection_count(self, ip_address):
        # 공인 IP 주소의 연결 수만 감소
        if not ipaddress.ip_address(ip_address).is_private:
            if ip_address in self.connection_counts:
                self.connection_counts[ip_address] -= 1
                if self.connection_counts[ip_address] <= 0:
                    del self.connection_counts[ip_address]