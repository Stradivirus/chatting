from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import json
import logging
import asyncio
from redis_manager import RedisManager

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

redis_manager = RedisManager()
active_connections = {}

message_history = {}
banned_users = set()

class UserCountManager:
    def __init__(self):
        self.user_count = 0
        self.lock = asyncio.Lock()

    async def increment(self):
        async with self.lock:
            self.user_count += 1
            logger.info(f"User count incremented to {self.user_count}")
            return self.user_count

    async def decrement(self):
        async with self.lock:
            self.user_count = max(0, self.user_count - 1)
            logger.info(f"User count decremented to {self.user_count}")
            return self.user_count

    async def get_count(self):
        async with self.lock:
            return self.user_count

user_count_manager = UserCountManager()

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

async def check_spam(client_id: str, message: str) -> bool:
    current_time = datetime.now()
    
    if client_id not in message_history:
        message_history[client_id] = []
    
    if message_history[client_id] and (current_time - message_history[client_id][-1]['time']).total_seconds() < 0.5:
        return True
    
    if len(message_history[client_id]) >= 2 and all(m['content'] == message for m in message_history[client_id][-2:]):
        return True
    
    if len(message) > 30:
        return True
    
    five_seconds_ago = current_time - timedelta(seconds=5)
    recent_messages = [m for m in message_history[client_id] if m['time'] > five_seconds_ago]
    if len(recent_messages) >= 8:
        return True
    
    message_history[client_id].append({'content': message, 'time': current_time})
    if len(message_history[client_id]) > 10:
        message_history[client_id] = message_history[client_id][-10:]
    
    return False

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    
    try:
        user_count = await user_count_manager.increment()
        logger.info(f"New client connected: {client_id}. Total users: {user_count}")
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

                await broadcast_message(message)
                await redis_manager.add_message_to_history(json.dumps(message))
                logger.debug(f"Broadcasted and stored message: {message}")
            except WebSocketDisconnect:
                logger.info(f"Client disconnected: {client_id}")
                break
            except Exception as e:
                logger.error(f"Error processing message from {client_id}: {str(e)}")
                break
    finally:
        if client_id in active_connections:
            del active_connections[client_id]
        if client_id in message_history:
            del message_history[client_id]
        user_count = await user_count_manager.decrement()
        await broadcast_user_count(user_count)
        logger.info(f"Connection closed for client: {client_id}. Total users: {user_count}")

async def broadcast_user_count(count):
    message = json.dumps({"type": "user_count", "count": count})
    logger.info(f"Broadcasting user count: {count}")
    await broadcast_message(message)

async def broadcast_message(message):
    if isinstance(message, dict):
        message = json.dumps(message)
    for connection in active_connections.values():
        await connection.send_text(message)

@app.on_event("startup")
async def startup_event():
    try:
        await redis_manager.connect()
        logger.info("Connected to Redis")
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