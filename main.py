from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime
import json
import logging
from redis_manager import RedisManager

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

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

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    logger.info(f"New client connected: {client_id}")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from {client_id}: {data}")
            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Redis에 메시지 발행
            await redis_manager.publish("chat", json.dumps(message))
            logger.debug(f"Published message to Redis: {message}")
            
            # 모든 연결된 클라이언트에게 메시지 브로드캐스트
            for conn_id, connection in active_connections.items():
                await connection.send_json(message)
                logger.debug(f"Sent message to client: {conn_id}")
    except WebSocketDisconnect:
        del active_connections[client_id]
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")

@app.on_event("startup")
async def startup_event():
    await redis_manager.connect()
    logger.info("Connected to Redis")

# 나머지 코드는 그대로 유지

@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    logger.info("Closed Redis connection")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)