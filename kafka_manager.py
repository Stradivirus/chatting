import os
import json
import asyncio
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
import logging
import aioredis  # Redis와의 비동기 연결을 위한 라이브러리

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.consumer_group_id = os.getenv("KAFKA_CONSUMER_GROUP_ID", "fastapi-chatting-pod")
        self.producer = None
        self.consumer = None
        self.redis = None
        self.topic_prefix = "chat-messages-"
        self.message_queue = asyncio.Queue()

    async def connect_producer(self):
        # Kafka producer에 연결
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                api_version="auto",
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
        # Kafka consumer에 연결 및 주어진 토픽 구독
        try:
            self.consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                api_version="auto",
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

    async def connect_redis(self):
        # Redis에 비동기 연결
        redis_host = os.getenv("REDIS_HOST", "redis-cluster.chat.svc.cluster.local")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        try:
            self.redis = await aioredis.from_url(f"redis://{redis_host}:{redis_port}", decode_responses=True)
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def get_messages_from_redis(self):
        # Redis에서 메시지를 가져와 Kafka에 전송
        if not self.redis:
            await self.connect_redis()

        try:
            async for message in self.redis.lrange("messages", 0, -1):  # 'messages' 리스트에서 모든 메시지를 가져옴
                logger.info(f"Fetched message from Redis: {message}")
                await self.produce_message(json.loads(message))  # 메시지를 Kafka에 전송
                await self.redis.lrem("messages", 0, message)  # Redis에서 메시지 삭제
        except Exception as e:
            logger.error(f"Failed to fetch messages from Redis: {e}")

    async def produce_message(self, message):
        # Kafka 토픽에 메시지 전송
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
        # Kafka 토픽에서 메시지 소비
        if not self.consumer:
            await self.connect_consumer(topic)

        try:
            async for message in self.consumer:
                logger.info(f"Received message: {message.value}")
                # 메시지 처리 로직 추가
        except KafkaError as e:
            logger.error(f"Error consuming messages from Kafka: {e}")
            raise

    async def kafka_message_handler(self):
        # 큐에서 메시지를 가져와 Kafka에 전송
        while True:
            try:
                message = await self.message_queue.get()
                await self.produce_message(message)
            except Exception as e:
                logger.error(f"Error handling Kafka message: {e}")
                await self.message_queue.put(message)  # 실패한 메시지를 다시 큐에 추가
            await asyncio.sleep(0.1)

    async def add_to_message_queue(self, message):
        # 메시지를 큐에 추가
        await self.message_queue.put(message)

    def get_topic_name(self):
        # 현재 시간에 기반하여 토픽 이름 생성
        from datetime import datetime
        date = datetime.now()
        return f"{self.topic_prefix}{date.strftime('%Y-%m-%d-%H-%M')}"

    async def close(self):
        # Kafka 및 Redis 연결 종료
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        if self.redis:
            await self.redis.close()
        logger.info("Kafka and Redis connections closed")
