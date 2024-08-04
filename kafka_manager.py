import os
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.producer = None
        self.consumer = None
        self.admin_client = None
        self.topic_prefix = "chat-messages-"

    def connect_producer(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: str(v).encode('utf-8')
            )
            logger.info(f"Kafka producer connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka producer: {e}")

    def connect_consumer(self, topic):
        try:
            self.consumer = KafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='chat-group',
                value_deserializer=lambda x: x.decode('utf-8')
            )
            logger.info(f"Kafka consumer connected to {self.bootstrap_servers} and subscribed to topic {topic}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka consumer: {e}")

    def connect_admin(self):
        try:
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=self.bootstrap_servers
            )
            logger.info(f"Kafka admin client connected to {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect Kafka admin client: {e}")

    def get_topic_name(self, date=None):
        if date is None:
            date = datetime.now()
        return f"{self.topic_prefix}{date.strftime('%Y-%m-%d')}"

    def create_topic_if_not_exists(self, topic_name):
        if not self.admin_client:
            self.connect_admin()
        try:
            new_topic = NewTopic(name=topic_name, num_partitions=1, replication_factor=1)
            self.admin_client.create_topics([new_topic])
            logger.info(f"Created new topic: {topic_name}")
        except TopicAlreadyExistsError:
            logger.info(f"Topic {topic_name} already exists")
        except KafkaError as e:
            logger.error(f"Failed to create topic {topic_name}: {e}")

    async def produce_message(self, message):
        if not self.producer:
            self.connect_producer()
        
        topic_name = self.get_topic_name()
        self.create_topic_if_not_exists(topic_name)
        
        try:
            future = self.producer.send(topic_name, value=message)
            record_metadata = await future
            logger.info(f"Message sent to topic {topic_name} at partition {record_metadata.partition} offset {record_metadata.offset}")
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}")

    async def consume_messages(self, days=1):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        topics = [self.get_topic_name(start_date + timedelta(days=i)) for i in range(days)]
        
        if not self.consumer:
            self.connect_consumer(topics)
        
        try:
            async for message in self.consumer:
                yield message.value
        except KafkaError as e:
            logger.error(f"Error consuming messages from Kafka: {e}")

    def delete_old_topics(self):
        if not self.admin_client:
            self.connect_admin()
        
        try:
            topics = self.admin_client.list_topics()
            week_ago = datetime.now() - timedelta(days=7)
            
            for topic in topics:
                if topic.startswith(self.topic_prefix):
                    topic_date_str = topic[len(self.topic_prefix):]
                    topic_date = datetime.strptime(topic_date_str, '%Y-%m-%d')
                    if topic_date < week_ago:
                        self.admin_client.delete_topics([topic])
                        logger.info(f"Deleted old topic: {topic}")
        except KafkaError as e:
            logger.error(f"Failed to delete old topics: {e}")

    def close(self):
        if self.producer:
            self.producer.close()
        if self.consumer:
            self.consumer.close()
        if self.admin_client:
            self.admin_client.close()
        logger.info("Kafka connections closed")

    async def manage_topics(self):
        while True:
            self.create_topic_if_not_exists(self.get_topic_name())
            self.delete_old_topics()
            await asyncio.sleep(86400)  # 24시간마다 실행