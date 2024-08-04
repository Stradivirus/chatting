import os
import json
import asyncio
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import logging
from redis_manager import RedisManager
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.producer = None
        self.topic_prefix = "chat-messages-"
        self.redis_manager = RedisManager()
        self.polling_interval = 1  # 1 second
        self.topic_creation_interval = 60  # 1 minute
        self.topic_retention_time = 300  # 5 minutes
        self.current_topic = None
        self.active_topics = []

    async def connect_producer(self):
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                enable_idempotence=True,
                acks='all',
            )
            await self.producer.start()
            logger.info(f"Kafka producer connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka producer: {e}")
            raise

    async def produce_message(self, message):
        if not self.producer:
            await self.connect_producer()

        try:
            await self.producer.send_and_wait(self.current_topic, message)
            logger.info(f"Successfully sent message to topic {self.current_topic}")
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}", exc_info=True)

    async def start_consuming_from_redis(self):
        last_topic_creation_time = datetime.now()

        while True:
            try:
                current_time = datetime.now()
                if (current_time - last_topic_creation_time).total_seconds() >= self.topic_creation_interval:
                    self.current_topic = self.create_new_topic()
                    self.manage_topics()
                    last_topic_creation_time = current_time

                messages = await self.redis_manager.get_new_messages()
                for message in messages:
                    await self.produce_message(message)
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Error in consuming messages from Redis: {e}")
                await asyncio.sleep(self.polling_interval)

    def create_new_topic(self):
        new_topic = f"{self.topic_prefix}{datetime.now().strftime('%Y-%m-%d-%H-%M')}"
        self.active_topics.append((new_topic, datetime.now()))
        logger.info(f"Created new topic: {new_topic}")
        return new_topic

    def manage_topics(self):
        current_time = datetime.now()
        self.active_topics = [(topic, created_time) for topic, created_time in self.active_topics 
                              if (current_time - created_time).total_seconds() <= self.topic_retention_time]
        logger.info(f"Active topics after management: {[topic for topic, _ in self.active_topics]}")

    async def close(self):
        if self.producer:
            await self.producer.stop()
        logger.info("Kafka connections closed")