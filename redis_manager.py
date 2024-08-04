import os
import json
import asyncio
import ipaddress
import time
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError
import aiohttp
import logging

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        # Redis 연결 정보 설정
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.pool = None
        self.pubsub = None
        self.blocked_ips = set()  # 차단된 IP 주소 저장
        self.connection_counts = {}  # IP별 연결 수 추적
        self.max_connections_per_ip = 3  # IP당 최대 연결 수

    async def connect(self):
        # Redis에 연결
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
                logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
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
        # 메시지 발행
        try:
            if not self.pool:
                await self.connect()
            return await self.redis.publish(channel, message)
        except RedisError as e:
            logger.error(f"Error publishing message: {e}")
            await self.reconnect()
            return await self.redis.publish(channel, message)

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
        # 연결 허용 여부 확인
        try:
            ip = ipaddress.ip_address(ip_address)
            
            if ip.is_private:
                logger.info(f"IP {ip_address} is private, allowing connection without restrictions")
                return True
            
            # 공인 IP에 대해서만 연결 수 제한 확인
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

    async def store_message(self, channel, message, expire_time=7200):
        # 메시지를 Redis에 저장하고 만료 시간 설정
        try:
            if not self.pool:
                await self.connect()
            
            # 메시지와 타임스탬프를 JSON으로 저장
            message_data = json.dumps({
                'message': message,
                'timestamp': int(time.time())
            })
            
            # 채널별로 고유한 키 생성
            key = f"chat:{channel}:{int(time.time())}"
            
            # 메시지 저장 및 만료 시간 설정
            await self.redis.set(key, message_data)
            await self.redis.expire(key, expire_time)
            
            return True
        except RedisError as e:
            logger.error(f"Error storing message: {e}")
            await self.reconnect()
            return False

    async def get_recent_messages(self, channel, limit=100):
        # 특정 채널의 최근 메시지 조회
        try:
            if not self.pool:
                await self.connect()
            
            # 채널의 모든 메시지 키 가져오기
            keys = await self.redis.keys(f"chat:{channel}:*")
            
            # 최근 메시지부터 정렬
            keys.sort(reverse=True)
            
            messages = []
            for key in keys[:limit]:
                message_data = await self.redis.get(key)
                if message_data:
                    messages.append(json.loads(message_data))
            
            return messages
        except RedisError as e:
            logger.error(f"Error retrieving messages: {e}")
            await self.reconnect()
            return []