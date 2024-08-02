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

    async def is_user_banned(self, username):
        ban_key = f"ban:{username}"
        return await self.redis.exists(ban_key)

    async def ban_user(self, username, duration=60):
        ban_key = f"ban:{username}"
        await self.redis.setex(ban_key, duration, 1)
        logger.info(f"User {username} banned for {duration} seconds")

    async def check_duplicate_message(self, username, message):
        key = f"last_message:{username}"
        last_message = await self.redis.get(key)
        
        if last_message == message:
            duplicate_count_key = f"duplicate_count:{username}"
            count = await self.redis.incr(duplicate_count_key)
            await self.redis.expire(duplicate_count_key, 60)  # 1분 후 만료
            logger.debug(f"Duplicate message from {username}. Count: {count}")
            return count
        else:
            await self.redis.set(key, message)
            await self.redis.delete(f"duplicate_count:{username}")
            return 0

    async def reset_duplicate_count(self, username):
        await self.redis.delete(f"duplicate_count:{username}")

    async def check_rate_limit(self, username):
        key = f'rate_limit:{username}'
        pipeline = self.redis.pipeline()
        
        pipeline.incr(key)
        pipeline.expire(key, 5)
        pipeline.get(key)
        
        _, _, message_count = await pipeline.execute()

        message_count = int(message_count) if message_count else 0
        if message_count > 8:
            await self.ban_user(username, 30)  # 1분 밴
            logger.warning(f"Rate limit exceeded for {username}. User banned for 1 minute.")
            return False
        
        return True

    async def check_spam(self, username, message):
        if await self.is_user_banned(username):
            return False, "현재 채팅이 제한되었습니다."

        duplicate_count = await self.check_duplicate_message(username, message)
        if duplicate_count >= 5:
            await self.ban_user(username, 30)  # 1분 밴
            return False, "도배 방지: 같은 메시지를 반복하지 마세요."

        if not await self.check_rate_limit(username):
            return False, "도배 방지: 너무 빠른 속도로 채팅을 보내고 있습니다."

        return True, None

    async def get_messages(self):
        return await self.redis.lrange("chat_messages", 0, -1)

    async def add_message(self, message):
        await self.redis.rpush("chat_messages", message)
        await self.redis.ltrim("chat_messages", -20, -1)  # 최근 20개 메시지만 유지