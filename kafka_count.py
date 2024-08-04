import os
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-count-svc:9092")
        self.producer = None
        self.consumer = None
        self.admin_client = None
        self.connection_count = 0
        self.update_task = None

    async def connect(self):
        try:
            self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
            await self.producer.start()
            self.admin_client = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
            await self.admin_client.start()
            logger.info("Connected to Kafka producer and admin client")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise

    async def disconnect(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        if self.admin_client:
            await self.admin_client.close()
        if self.update_task:
            self.update_task.cancel()

    async def send_count_update(self):
        try:
            await self.producer.send_and_wait("connection_count", json.dumps({
                "count": self.connection_count
            }).encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to send count update to Kafka: {e}")
            raise

    async def consume_count_updates(self, callback):
        self.consumer = AIOKafkaConsumer("connection_count", bootstrap_servers=self.bootstrap_servers)
        await self.consumer.start()
        try:
            async for msg in self.consumer:
                await callback(json.loads(msg.value.decode('utf-8')))
        finally:
            await self.consumer.stop()

    async def create_topic(self, topic_name, num_partitions=1, replication_factor=1):
        try:
            topics = await self.admin_client.list_topics()
            if topic_name not in topics:
                new_topic = NewTopic(
                    name=topic_name,
                    num_partitions=num_partitions,
                    replication_factor=replication_factor
                )
                await self.admin_client.create_topics([new_topic])
                logger.info(f"Created Kafka topic: {topic_name}")
            else:
                logger.info(f"Kafka topic already exists: {topic_name}")
        except Exception as e:
            logger.error(f"Failed to create Kafka topic: {e}")
            raise

    async def update_connection_count(self, change):
        self.connection_count += change
        await self.send_count_update()

    async def periodic_count_update(self):
        while True:
            await asyncio.sleep(1)  # 1초 대기
            await self.send_count_update()

    async def start_count_updates(self):
        self.update_task = asyncio.create_task(self.periodic_count_update())

    def stop_count_updates(self):
        if self.update_task:
            self.update_task.cancel()