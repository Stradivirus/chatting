import os
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError
import logging
from datetime import datetime, timedelta
import asyncio

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        # Kafka 서버 주소 설정
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.producer = None
        self.consumer = None
        self.admin_client = None
        self.topic_prefix = "chat-messages-"

    async def connect_producer(self):
        # Kafka 프로듀서 연결
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: str(v).encode('utf-8')
            )
            await self.producer.start()
            logger.info(f"Kafka producer connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka producer: {e}")

    async def connect_consumer(self, topic):
        # Kafka 컨슈머 연결
        try:
            self.consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='chat-group',
                value_deserializer=lambda x: x.decode('utf-8')
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer connected to {self.bootstrap_servers} and subscribed to topic {topic}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka consumer: {e}")

    async def connect_admin(self):
        # Kafka 관리자 클라이언트 연결
        try:
            self.admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers
            )
            logger.info(f"Kafka admin client connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka admin client: {e}")

    def get_topic_name(self, date=None):
        # 분 단위로 토픽 이름 생성
        if date is None:
            date = datetime.now()
        return f"{self.topic_prefix}{date.strftime('%Y-%m-%d-%H-%M')}"

    async def create_topic_if_not_exists(self, topic_name):
        # 토픽이 존재하지 않으면 생성
        if not self.admin_client:
            logger.info("Admin client not connected. Connecting now.")
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

    async def produce_message(self, message):
        # 메시지 생산
        if not self.producer:
            logger.info("Producer not connected. Connecting now.")
            await self.connect_producer()
        
        topic_name = self.get_topic_name()
        logger.info(f"Producing message to topic: {topic_name}")
        await self.create_topic_if_not_exists(topic_name)
        
        try:
            await self.producer.send_and_wait(topic_name, message)
            logger.info(f"Successfully sent message to topic {topic_name}")
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}", exc_info=True)

    async def consume_messages(self, days=1):
        # 메시지 소비
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

    async def delete_old_topics(self):
        # 5분 이상 된 토픽 삭제
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

    async def close(self):
        # Kafka 연결 종료
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        if self.admin_client:
            await self.admin_client.close()
        logger.info("Kafka connections closed")

    async def manage_topics(self):
        # 1분마다 토픽 관리
        while True:
            current_topic = self.get_topic_name()
            logger.info(f"Starting topic management cycle. Current topic: {current_topic}")
            await self.create_topic_if_not_exists(current_topic)
            await self.delete_old_topics()
            logger.info("Topic management cycle completed. Waiting for next cycle.")
            await asyncio.sleep(60)  # 1분마다 실행