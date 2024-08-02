from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime
import json
import logging
import asyncio
from redis_manager import RedisManager

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

redis_manager = RedisManager()
active_connections = {}

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

async def broadcast_messages():
    await redis_manager.subscribe("chat")
    async for message in redis_manager.listen():
        await asyncio.gather(
            *[connection.send_text(json.dumps(message)) for connection in active_connections.values()],
            return_exceptions=True
        )
        logger.debug(f"Broadcasted message to all clients: {message}")

async def check_spam(client_id: str, message: str) -> bool:
    spam_key = f"spam:{client_id}"
    block_key = f"block:{client_id}"
    
    # 차단 여부 확인
    block_time = await redis_manager.get(block_key)
    if block_time:
        remaining_time = max(0, int(float(block_time)))
        return True, remaining_time

    # 최근 메시지 가져오기
    recent_messages = await redis_manager.lrange(spam_key, 0, -1)
    
    # 같은 메시지가 연속으로 3번 이상 있는지 확인
    if len(recent_messages) >= 2 and all(msg == message for msg in recent_messages[-2:]):
        # 차단 설정
        await redis_manager.setex(block_key, 10, "10")
        return True, 10

    # 새 메시지 추가 및 오래된 메시지 제거
    await redis_manager.lpush(spam_key, message)
    await redis_manager.ltrim(spam_key, 0, 2)
    
    return False, 0

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    logger.info(f"New client connected: {client_id}")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from {client_id}: {data}")
            
            is_spam, remaining_time = await check_spam(client_id, data)
            if is_spam:
                warning = {
                    "type": "warning",
                    "message": f"도배 방지: {remaining_time}초 동안 채팅이 금지됩니다.",
                    "remainingTime": remaining_time
                }
                await websocket.send_text(json.dumps(warning))
                logger.warning(f"Spam detected from {client_id}")
                continue
            
            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }

            await redis_manager.publish("chat", json.dumps(message))
            logger.debug(f"Published message to Redis: {message}")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")
    finally:
        if client_id in active_connections:
            del active_connections[client_id]
        logger.info(f"Connection closed for client: {client_id}")

@app.on_event("startup")
async def startup_event():
    try:
        await redis_manager.connect()
        logger.info("Connected to Redis")
        asyncio.create_task(broadcast_messages())
        logger.info("Started message broadcasting task")
    except Exception as e:
        logger.error(f"Failed to start up properly: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    logger.info("Closed Redis connection")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)