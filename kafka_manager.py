from aiokafka import AIOKafkaProducer
import os
import json

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
        self.producer = None

    async def connect(self):
        if not self.producer:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await self.producer.start()

    async def produce(self, topic, message):
        await self.connect()
        await self.producer.send_and_wait(topic, message)

    async def close(self):
        if self.producer:
            await self.producer.stop()