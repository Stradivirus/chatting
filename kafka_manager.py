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
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.consumer_group_id = os.getenv("KAFKA_CONSUMER_GROUP_ID", "fastapi-chatting-pod")  # Consumer Group ID 설정
        self.producer = None
        self.consumer = None
        self.admin_client = None
        self.topic_prefix = "chat-messages-"
        self.message_queue = asyncio.Queue()

    async def connect_producer(self):
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                api_version="auto",
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
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
                group_id=self.consumer_group_id,  # Consumer Group ID 사용
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

    async def create_topic_if_not_exists(self, topic_name):
        if not self.admin_client:
            await self.connect_admin()
        try:
            logger.info(f"Attempting to create topic: {topic_name}")
            new_topic = NewTopic(name=topic_name, num_partitions=1, replication_factor=1)
            await self.admin_client.create_topics([new_topic])
            logger.info(f"Successfully created new topic: {topic_name}")
        except TopicAlreadyExistsError:
            logger.info(f"Topic {topic_name} already exists")
        except KafkaError as e:
            logger.error(f"Failed to create topic {topic_name}: {e}", exc_info=True)
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

    async def consume_messages(self, days=1):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        topics = [self.get_topic_name(start_date + timedelta(minutes=i)) for i in range(days*24*60)]
        
        if not self.consumer:
            await self.connect_consumer(topics)
        
        try:
            async for message in self.consumer:
                yield message.value
        except KafkaError as e:
            logger.error(f"Error consuming messages from Kafka: {e}")
            raise

    async def delete_old_topics(self):
        if not self.admin_client:
            await self.connect_admin()
        
        try:
            topics = await self.admin_client.list_topics()
            five_minutes_ago = datetime.now() - timedelta(minutes=5)
            
            logger.info(f"Checking for topics older than 5 minutes to delete")
            for topic in topics:
                if topic.startswith(self.topic_prefix):
                    topic_date_str = topic[len(self.topic_prefix):]
                    topic_date = datetime.strptime(topic_date_str, '%Y-%m-%d-%H-%M')
                    if topic_date < five_minutes_ago:
                        logger.info(f"Attempting to delete old topic: {topic}")
                        await self.admin_client.delete_topics([topic])
                        logger.info(f"Successfully deleted old topic: {topic}")
        except KafkaError as e:
            logger.error(f"Failed to delete old topics: {e}", exc_info=True)
            raise

    async def close(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        if self.admin_client:
            await self.admin_client.close()
        logger.info("Kafka connections closed")

    async def manage_topics(self):
        while True:
            try:
                current_topic = self.get_topic_name()
                logger.info(f"Starting topic management cycle. Current topic: {current_topic}")
                await self.create_topic_if_not_exists(current_topic)
                await self.delete_old_topics()
                logger.info("Topic management cycle completed. Waiting for next cycle.")
            except Exception as e:
                logger.error(f"Error in topic management cycle: {e}", exc_info=True)
            finally:
                await asyncio.sleep(300)  # 5분마다 실행
    
    async def kafka_message_handler(self):
        while True:
            try:
                message = await self.message_queue.get()
                await self.produce_message(message)
            except Exception as e:
                logger.error(f"Error handling Kafka message: {e}")
                await self.message_queue.put(message)  # 실패한 메시지를 다시 큐에 추가
            await asyncio.sleep(0.1)

    async def add_to_message_queue(self, message):
        await self.message_queue.put(message)
