import os
import json
import asyncio
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer, AIOKafkaAdminClient
from aiokafka.errors import KafkaError
from aiokafka.admin import NewTopic
import logging
from redis_manager import RedisManager
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.consumer_group_id = os.getenv("KAFKA_CONSUMER_GROUP_ID", "fastapi-chatting-pod")
        self.producer = None
        self.admin_client = None
        self.topic_prefix = "chat-messages-"
        self.redis_manager = RedisManager()
        self.polling_interval = 1  # 1 second
        self.topic_creation_interval = 60  # 1 minute
        self.topic_retention_time = 300  # 5 minutes

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

    async def connect_admin(self):
        try:
            self.admin_client = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
            await self.admin_client.start()
            logger.info(f"Kafka admin client connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka admin client: {e}")
            raise

    async def create_topic(self):
        topic_name = self.get_topic_name()
        try:
            new_topic = NewTopic(
                name=topic_name,
                num_partitions=1,
                replication_factor=1
            )
            await self.admin_client.create_topics([new_topic])
            logger.info(f"Created new topic: {topic_name}")
        except KafkaError as e:
            logger.error(f"Failed to create topic {topic_name}: {e}")

    async def delete_old_topics(self):
        try:
            topics = await self.admin_client.list_topics()
            current_time = datetime.now()
            for topic in topics:
                if topic.startswith(self.topic_prefix):
                    topic_time = datetime.strptime(topic[len(self.topic_prefix):], '%Y-%m-%d-%H-%M')
                    if (current_time - topic_time).total_seconds() > self.topic_retention_time:
                        await self.admin_client.delete_topics([topic])
                        logger.info(f"Deleted old topic: {topic}")
        except KafkaError as e:
            logger.error(f"Failed to delete old topics: {e}")

    async def produce_message(self, message):
        if not self.producer:
            await self.connect_producer()

        topic_name = self.get_topic_name()

        try:
            await self.producer.send_and_wait(topic_name, message)
            logger.info(f"Successfully sent message to topic {topic_name}")
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}", exc_info=True)

    async def start_consuming_from_redis(self):
        if not self.admin_client:
            await self.connect_admin()

        last_topic_creation_time = datetime.now()

        while True:
            try:
                current_time = datetime.now()
                if (current_time - last_topic_creation_time).total_seconds() >= self.topic_creation_interval:
                    await self.create_topic()
                    await self.delete_old_topics()
                    last_topic_creation_time = current_time

                messages = await self.redis_manager.get_new_messages()  # 새로운 메시지만 가져옴
                for message in messages:
                    await self.produce_message(message)
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Error in consuming messages from Redis: {e}")
                await asyncio.sleep(self.polling_interval)

    def get_topic_name(self):
        date = datetime.now()
        return f"{self.topic_prefix}{date.strftime('%Y-%m-%d-%H-%M')}"

    async def close(self):
        if self.producer:
            await self.producer.stop()
        if self.admin_client:
            await self.admin_client.close()
        logger.info("Kafka connections closed")