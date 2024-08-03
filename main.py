from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import json
import logging
import asyncio
from redis_manager import RedisManager

class UserCountManager:
    def __init__(self):
        self.user_count = 0
        self.lock = asyncio.Lock()

    async def increment(self):
        async with self.lock:
            self.user_count += 1
            return self.user_count

    async def decrement(self):
        async with self.lock:
            self.user_count = max(0, self.user_count - 1)
            return self.user_count

    async def get_count(self):
        async with self.lock:
            return self.user_count
        
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

redis_manager = RedisManager()
active_connections = {}

message_history = {}
banned_users = set()

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
        # 메시지를 Redis에 저장
        await redis_manager.add_message_to_history(json.dumps(message))
        logger.debug(f"Broadcasted and stored message: {message}")

async def check_spam(client_id: str, message: str) -> bool:
    # 기존 스팸 체크 로직 유지
    ...

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    client_ip = websocket.client.host
    
    if not await redis_manager.is_allowed_connection(client_ip):
        await websocket.close(code=1008, reason="Connection not allowed")
        return

    try:
        await websocket.accept()
        redis_manager.increment_connection_count(client_ip)
        active_connections[client_id] = websocket
        logger.info(f"New client connected: {client_id} from IP: {client_ip}")
        
        user_count = await user_count_manager.increment()
        await broadcast_user_count(user_count)
        
        while True:
            try:
                data = await websocket.receive_text()
                logger.debug(f"Received message from {client_id}: {data}")
                
                if client_id in banned_users:
                    warning = {
                        "type": "warning",
                        "message": "You are currently banned from sending messages."
                    }
                    await websocket.send_text(json.dumps(warning))
                    continue
                
                if await check_spam(client_id, data):
                    banned_users.add(client_id)
                    warning = {
                        "type": "warning",
                        "message": "You have been banned for 30 seconds due to spamming."
                    }
                    await websocket.send_text(json.dumps(warning))
                    await asyncio.sleep(30)
                    banned_users.remove(client_id)
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
                break
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from client: {client_id}")
            except asyncio.CancelledError:
                logger.info(f"WebSocket connection cancelled for client: {client_id}")
                break
            except Exception as e:
                logger.error(f"Error processing message from {client_id}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")
    finally:
        if client_id in active_connections:
            del active_connections[client_id]
        redis_manager.decrement_connection_count(client_ip)
        user_count = await user_count_manager.decrement()
        await broadcast_user_count(user_count)
        logger.info(f"Connection closed for client: {client_id}")

async def broadcast_user_count(count):
    message = json.dumps({"type": "user_count", "count": count})
    for connection in active_connections.values():
        await connection.send_text(message)
async def broadcast_user_count(count):
    message = json.dumps({"type": "user_count", "count": count})
    for connection in active_connections.values():
        await connection.send_text(message)

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