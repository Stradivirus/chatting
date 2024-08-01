from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
import os
import asyncio
from RedisManager import RedisManager

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

# 활성 WebSocket 연결을 저장할 집합
active_connections = set()

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

async def redis_listener():
    await redis_manager.connect()
    channel = await redis_manager.redis.subscribe("chat")
    try:
        while True:
            message = await channel[0].get()
            if message:
                await broadcast(json.loads(message))
    finally:
        await redis_manager.close()

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
            await redis_manager.publish("chat", json.dumps(message))
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    finally:
        active_connections.remove(websocket)

async def broadcast(message: dict):
    for connection in active_connections:
        await connection.send_json(message)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)