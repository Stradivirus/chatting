import os
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.producer = None
        self.consumer = None

    async def connect(self):
        try:
            self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
            await self.producer.start()
            logger.info("Connected to Kafka producer")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka producer: {e}")
            raise

    async def disconnect(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()

    async def send_message(self, topic, message):
        try:
            await self.producer.send_and_wait(topic, json.dumps(message).encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to send message to Kafka: {e}")
            raise

    async def consume_messages(self, topic, callback):
        self.consumer = AIOKafkaConsumer(topic, bootstrap_servers=self.bootstrap_servers)
        await self.consumer.start()
        try:
            async for msg in self.consumer:
                await callback(json.loads(msg.value.decode('utf-8')))
        finally:
            await self.consumer.stop()