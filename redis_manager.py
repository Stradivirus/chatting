import os
import json
import asyncio
from redis.asyncio import Redis
from datetime import datetime, timedelta

class RedisManager:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis = None
        self.pubsub = None

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
        await self.add_message_to_history(message)

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

    async def add_message_to_history(self, message):
        await self.redis.lpush("chat_history", json.dumps(message))
        await self.redis.ltrim("chat_history", 0, 19)  # Keep only the latest 20 messages

    async def get_chat_history(self):
        history = await self.redis.lrange("chat_history", 0, -1)
        return [json.loads(msg) for msg in history][::-1]  # Reverse to get chronological order

    async def check_and_update_user_messages(self, client_id, message):
        key = f"user_messages:{client_id}"
        current_time = datetime.now().timestamp()
        
        # Remove messages older than 5 seconds
        await self.redis.zremrangebyscore(key, 0, current_time - 5)
        
        # Add the new message
        await self.redis.zadd(key, {message: current_time})
        
        # Get the count of messages in the last 5 seconds
        count = await self.redis.zcount(key, current_time - 5, current_time)
        
        if count >= 3:
            await self.redis.set(f"user_blocked:{client_id}", "1", ex=5)  # Block for 5 seconds
            return False
        
        return True

    async def is_user_blocked(self, client_id):
        return await self.redis.get(f"user_blocked:{client_id}") is not None