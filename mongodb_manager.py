from motor.motor_asyncio import AsyncIOMotorClient
import os

class MongoManager:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        mongodb_uri = os.getenv("MONGODB_URI")
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client.chat_db

    async def save_message(self, message):
        if not self.db:
            await self.connect()
        await self.db.messages.insert_one(message)

    async def get_recent_messages(self, limit=50):
        if not self.db:
            await self.connect()
        cursor = self.db.messages.find().sort('timestamp', -1).limit(limit)
        messages = await cursor.to_list(length=limit)
        return list(reversed(messages))

    async def close(self):
        if self.client:
            self.client.close()