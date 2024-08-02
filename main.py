from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
import os
import asyncio
from redis_manager import RedisManager

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

# Redis 매니저 초기화
redis_manager = RedisManager()

# 활성 WebSocket 연결을 저장할 딕셔너리
active_connections = {}

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

async def redis_listener():
    await redis_manager.connect()
    pubsub = redis_manager.redis.pubsub()
    await pubsub.subscribe("chat")
    try:
        async for message in pubsub.listen():
            if message['type'] == 'message':
                await broadcast(json.loads(message['data']))
    finally:
        await pubsub.unsubscribe("chat")
        await redis_manager.close()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            # 수정: 60초 타임아웃 추가
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Redis에 메시지 발행
            await redis_manager.publish("chat", json.dumps(message))
    # 수정: 타임아웃 예외 처리 추가
    except asyncio.TimeoutError:
        # 타임아웃 발생 시 ping 메시지 전송
        await websocket.send_text("ping")
    except WebSocketDisconnect:
        del active_connections[client_id]
    finally:
        if client_id in active_connections:
            del active_connections[client_id]

async def broadcast(message: dict):
    for client_id, connection in active_connections.items():
        try:
            await connection.send_json(message)
        except WebSocketDisconnect:
            del active_connections[client_id]

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())

# 수정: Ping 처리를 위한 새로운 엔드포인트 추가
@app.websocket("/ping")
async def ping(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            await websocket.receive_text()
            await websocket.send_text("pong")
        except WebSocketDisconnect:
            break

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)