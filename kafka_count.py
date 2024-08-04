import asyncio
import os
import json
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KafkaManager:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-count-svc:9092").replace('"', '')
        self.producer = None
        self.consumer = None
        self.connection_count = 0
        self.update_task = None
        
    async def connect(self):
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.producer.start()
        self.consumer = AIOKafkaConsumer("connection_count", bootstrap_servers=self.bootstrap_servers)
        await self.consumer.start()
        logger.info("Connected to Kafka")

    async def disconnect(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        if self.update_task:
            self.update_task.cancel()

    async def send_count_update(self):
        try:
            await self.producer.send_and_wait("connection_count", json.dumps({"count": self.connection_count}).encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to send count update to Kafka: {e}")

    async def update_connection_count(self):
        while True:
            await asyncio.sleep(1)  # 1초 대기
            # 여기서 실제 접속자 수를 계산하는 로직을 추가할 수 있습니다.
            # 예를 들어, 웹소켓 연결 수를 세는 등의 방법으로 실제 접속자 수를 파악할 수 있습니다.
            # 현재는 예시를 위해 랜덤하게 변경하도록 하겠습니다.
            self.connection_count = max(0, self.connection_count + random.randint(-1, 1))
            await self.send_count_update()
            logger.info(f'Updated connection count: {self.connection_count}')

    async def start_updates(self):
        self.update_task = asyncio.create_task(self.update_connection_count())

    async def consume_updates(self):
        async for msg in self.consumer:
            data = json.loads(msg.value.decode('utf-8'))
            self.connection_count = data['count']
            logger.info(f'Received connection count update: {self.connection_count}')

async def main():
    manager = KafkaManager()
    await manager.connect()
    try:
        await asyncio.gather(
            manager.start_updates(),
            manager.consume_updates()
        )
    finally:
        await manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
