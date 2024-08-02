import os
import json
import asyncio
import time
import logging
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.pool = None
        self.pubsub = None
        self.redis = None

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
                logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            except RedisError as e:
                logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
                await self.reconnect()

    async def reconnect(self, max_retries=3):
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                await self.connect()
                return
            except RedisError as e:
                logger.error(f"Reconnection attempt {attempt + 1} failed: {e}", exc_info=True)
        raise Exception("Failed to reconnect to Redis after multiple attempts")

    async def publish(self, channel, message):
        try:
            if not self.redis:
                await self.connect()
            return await self.redis.publish(channel, message)
        except RedisError as e:
            logger.error(f"Error publishing message: {e}", exc_info=True)
            await self.reconnect()
            return await self.redis.publish(channel, message)

    async def subscribe(self, channel):
        try:
            if not self.pubsub:
                await self.connect()
            await self.pubsub.subscribe(channel)
        except RedisError as e:
            logger.error(f"Error subscribing to channel: {e}", exc_info=True)
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
                logger.error(f"Error while listening: {e}", exc_info=True)
                await self.reconnect()
            except Exception as e:
                logger.error(f"Unexpected error while listening: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def close(self):
        if self.pool:
            await self.pool.disconnect()
        logger.info("Closed Redis connection")

    async def check_spam(self, client_id, message):
        try:
            # 1. 같은 채팅 5번 반복 체크
            repeat_key = f"repeat:{client_id}"
            last_message_key = f"last_message:{client_id}"
            last_message = await self.redis.get(last_message_key)
            
            if last_message == message:
                repeat_count = await self.redis.incr(repeat_key)
            else:
                repeat_count = 1
                await self.redis.set(repeat_key, repeat_count)
            
            await self.redis.expire(repeat_key, 5)  # 5초 후 만료
            await self.redis.set(last_message_key, message)

            logger.debug(f"Repeat count for {client_id}: {repeat_count}")

            if repeat_count >= 5:
                await self.redis.setex(f"spam_block:{client_id}", 5, "repeat")
                logger.warning(f"Spam detected: repeated message from {client_id}")
                return False, "도배 방지: 같은 메시지를 반복하지 마세요."

            # 2. 5초에 8번 이상 채팅 체크
            freq_key = f"freq:{client_id}"
            freq_count = await self.redis.incr(freq_key)
            if freq_count == 1:
                await self.redis.expire(freq_key, 5)  # 5초 후 만료

            logger.debug(f"Frequency count for {client_id}: {freq_count}")

            if freq_count > 8:
                await self.redis.setex(f"spam_block:{client_id}", 10, "frequency")
                logger.warning(f"Spam detected: high frequency from {client_id}")
                return False, "도배 방지: 너무 빠른 속도로 채팅을 보내고 있습니다."

            return True, None
        except RedisError as e:
            logger.error(f"Error checking spam: {e}", exc_info=True)
            return True, None  # 에러 발생 시 기본적으로 허용

    async def is_blocked(self, client_id):
        try:
            blocked = await self.redis.get(f"spam_block:{client_id}")
            logger.debug(f"Block status for {client_id}: {'Blocked' if blocked else 'Not blocked'}")
            return blocked is not None
        except RedisError as e:
            logger.error(f"Error checking block status: {e}", exc_info=True)
            return False