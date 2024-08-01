from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import redis
from kafka import KafkaProducer
from datetime import datetime
import json
import os

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영 환경에서는 구체적인 오리진을 지정하세요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static 파일 서빙
app.mount("/static", StaticFiles(directory="static"), name="static")

# Redis 연결
redis_host = os.getenv("REDIS_HOST", "redis-service")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# Kafka 프로듀서 설정
kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-service:9092")
kafka_producer = KafkaProducer(
    bootstrap_servers=[kafka_bootstrap_servers],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# 활성 WebSocket 연결을 저장할 집합
active_connections = set()

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Redis에 메시지 발행
            redis_client.publish("chat", json.dumps(message))
            
            # Kafka에 메시지 전송
            topic = f"chat-{datetime.now().strftime('%Y-%m-%d')}"
            kafka_producer.send(topic, value=message)
            
            # 모든 연결된 클라이언트에게 메시지 브로드캐스트
            await broadcast(message)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    finally:
        # 연결이 종료되면 집합에서 제거
        active_connections.remove(websocket)

async def broadcast(message: dict):
    for connection in active_connections:
        await connection.send_json(message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)