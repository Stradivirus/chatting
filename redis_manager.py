from redis.cluster import RedisCluster
import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis_nodes = [
            {"host": "redis-0.redis-service.chat.svc.cluster.local", "port": 6379},
            {"host": "redis-1.redis-service.chat.svc.cluster.local", "port": 6379},
            {"host": "redis-2.redis-service.chat.svc.cluster.local", "port": 6379},
            {"host": "redis-3.redis-service.chat.svc.cluster.local", "port": 6379},
            {"host": "redis-4.redis-service.chat.svc.cluster.local", "port": 6379},
            {"host": "redis-5.redis-service.chat.svc.cluster.local", "port": 6379},
        ]
        self.redis = None
        self.pubsub = None

    async def connect(self, max_retries=5, retry_delay=5):
        for attempt in range(max_retries):
            try:
                self.redis = RedisCluster(startup_nodes=self.redis_nodes, decode_responses=True)
                # RedisCluster는 비동기 방식이 아니므로 ping을 동기 방식으로 호출합니다.
                if self.redis.ping():
                    logger.info(f"Successfully connected to Redis cluster")
                self.pubsub = self.redis.pubsub()
                return
            except Exception as e:
                logger.error(f"Failed to connect to Redis (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        raise Exception("Failed to connect to Redis after multiple attempts")

    async def publish(self, channel, message):
        try:
            if not self.redis:
                await self.connect()
            self.redis.publish(channel, message)
        except Exception as e:
            logger.error(f"Error publishing message: {str(e)}")
            raise

    async def subscribe(self, channel):
        try:
            if not self.pubsub:
                await self.connect()
            self.pubsub.subscribe(channel)
        except Exception as e:
            logger.error(f"Error subscribing to channel: {str(e)}")
            raise

    async def listen(self):
        if not self.pubsub:
            raise Exception("Not subscribed to any channel")
        while True:
            try:
                message = self.pubsub.get_message(ignore_subscribe_messages=True)
                if message is not None:
                    yield json.loads(message['data'])
            except Exception as e:
                logger.error(f"Error while listening for messages: {str(e)}")
                await asyncio.sleep(1)  # Wait a bit before retrying

    async def close(self):
        if self.redis:
            self.redis.close()
            logger.info("Closed Redis connection")