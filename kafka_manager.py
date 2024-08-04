import os
import json
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaError, TopicAlreadyExistsError
import logging
from datetime import datetime, timedelta
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self, topic_retention_minutes=5):  # 5분으로 설정
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.consumer_group_id = os.getenv("KAFKA_CONSUMER_GROUP_ID", "fastapi-chatting-pod")
        self.producer = None
        self.consumer = None
        self.admin_client = None
        self.topic_prefix = "chat-messages-"
        self.message_queue = asyncio.Queue()
        self.topic_retention_minutes = topic_retention_minutes

    async def connect_producer(self):
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                api_version="auto",
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
            )
            await self.producer.start()
            logger.info(f"Kafka producer connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka producer: {e}")
            raise

    async def connect_consumer(self, topics):
        try:
            self.consumer = AIOKafkaConsumer(
                bootstrap_servers=self.bootstrap_servers,
                api_version="auto",
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id=self.consumer_group_id,
                value_deserializer=lambda x: x.decode('utf-8')
            )
            await self.consumer.start()
            await self.consumer.subscribe(topics)
            logger.info(f"Kafka consumer connected to {self.bootstrap_servers} and subscribed to topics {topics}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka consumer: {e}")
            raise

    async def connect_admin(self):
        try:
            self.admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers,
                api_version="auto"
            )
            logger.info(f"Kafka admin client connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka admin client: {e}")
            raise

    def get_topic_name(self, date=None):
        if date is None:
            date = datetime.now()
        return f"{self.topic_prefix}{date.strftime('%Y-%m-%d-%H-%M')}"

    async def delete_old_topics(self):
        if not self.admin_client:
            await self.connect_admin()
        
        try:
            topics = await self.admin_client.list_topics()
            deletion_threshold = datetime.now() - timedelta(minutes=self.topic_retention_minutes)
            
            for topic in topics:
                if topic.startswith(self.topic_prefix):
                    topic_date_str = topic[len(self.topic_prefix):]
                    try:
                        topic_date = datetime.strptime(topic_date_str, '%Y-%m-%d-%H-%M')
                        if topic_date < deletion_threshold:
                            logger.info(f"Deleting old topic: {topic}")
                            await self.admin_client.delete_topics([topic])
                    except ValueError:
                        logger.warning(f"Could not parse date from topic name: {topic}")
        except KafkaError as e:
            logger.error(f"Failed to delete old topics: {e}", exc_info=True)

    async def manage_topics(self):
        while True:
            try:
                current_topic = self.get_topic_name()
                logger.info(f"Starting topic management cycle. Current topic: {current_topic}")
                await self.delete_old_topics()
                logger.info("Topic management cycle completed.")
            except Exception as e:
                logger.error(f"Error in topic management cycle: {e}", exc_info=True)
            finally:
                await asyncio.sleep(300)  # 5분마다 실행

    async def start_background_tasks(self):
        asyncio.create_task(self.manage_topics())

    async def produce_message(self, message):
        if not self.producer:
            await self.connect_producer()
        
        topic_name = self.get_topic_name()
        
        try:
            await self.producer.send_and_wait(topic_name, message)
            logger.info(f"Successfully sent message to topic {topic_name}")
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}", exc_info=True)
            await self.message_queue.put(message)

    async def consume_messages(self, days=1):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        topics = [self.get_topic_name(start_date + timedelta(minutes=i)) for i in range(days*24*60)]
        
        if not self.consumer:
            await self.connect_consumer(topics)
        
        try:
            async for message in self.consumer:
                logger.info(f"Received message: {message.value}")
        except KafkaError as e:
            logger.error(f"Error consuming messages from Kafka: {e}")
            raise

    async def start_consuming(self):
        while True:
            try:
                await self.consume_messages()
            except Exception as e:
                logger.error(f"Error in consume_messages: {e}")
            await asyncio.sleep(60)

    async def kafka_message_handler(self):
        while True:
            try:
                message = await self.message_queue.get()
                await self.produce_message(message)
            except Exception as e:
                logger.error(f"Error handling Kafka message: {e}")
                await self.message_queue.put(message)
            await asyncio.sleep(0.1)

    async def add_to_message_queue(self, message):
        await self.message_queue.put(message)

    async def close(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        if self.admin_client:
            await self.admin_client.close()
        logger.info("Kafka connections closed")
