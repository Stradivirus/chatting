import os
import json
import asyncio
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
import logging
from redis_manager import RedisManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.consumer_group_id = os.getenv("KAFKA_CONSUMER_GROUP_ID", "fastapi-chatting-pod")
        self.producer = None
        self.consumer = None
        self.topic_prefix = "chat-messages-"
        self.message_queue = asyncio.Queue()
        self.redis_manager = RedisManager()
        self.polling_interval = 1  # 1 second

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

    async def connect_consumer(self, topic):
        try:
            self.consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id=self.consumer_group_id,
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer connected to {self.bootstrap_servers} and subscribed to topic {topic}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka consumer: {e}")
            raise

    async def produce_message(self, message):
        if not self.producer:
            await self.connect_producer()

        topic_name = self.get_topic_name()

        try:
            await self.producer.send_and_wait(topic_name, message)
            logger.info(f"Successfully sent message to topic {topic_name}")
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}", exc_info=True)
            await self.message_queue.put(message)  # 실패한 메시지를 큐에 추가

    async def consume_messages(self, topic):
        if not self.consumer:
            await self.connect_consumer(topic)

        try:
            async for message in self.consumer:
                logger.info(f"Received message: {message.value}")
                # 메시지 처리 로직 추가 (필요한 경우)
        except KafkaError as e:
            logger.error(f"Error consuming messages from Kafka: {e}")
            raise

    async def start_consuming_from_redis(self):
        while True:
            try:
                messages = await self.redis_manager.get_messages(100)  # 최대 100개의 메시지를 가져옴
                for message in messages:
                    await self.produce_message(message)
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Error in consuming messages from Redis: {e}")
                await asyncio.sleep(self.polling_interval)

    async def kafka_message_handler(self):
        while True:
            try:
                message = await self.message_queue.get()
                await self.produce_message(message)
            except Exception as e:
                logger.error(f"Error handling Kafka message: {e}")
                await self.message_queue.put(message)  # 실패한 메시지를 다시 큐에 추가
            await asyncio.sleep(0.1)

    def get_topic_name(self):
        from datetime import datetime
        date = datetime.now()
        return f"{self.topic_prefix}{date.strftime('%Y-%m-%d-%H-%M')}"

    async def close(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        logger.info("Kafka connections closed")