from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime
import json
import logging
import asyncio
from redis_manager import RedisManager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

redis_manager = RedisManager()
active_connections = set()

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

async def broadcast_messages():
    await redis_manager.subscribe("chat")
    logger.info("Subscribed to 'chat' channel")
    async for message in redis_manager.listen():
        try:
            message_data = json.loads(message) if isinstance(message, str) else message
            for connection in active_connections:
                await connection.send_json(message_data)
            logger.debug(f"Broadcasted message to clients: {message_data}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse message: {message}")
        except Exception as e:
            logger.error(f"Error broadcasting message: {str(e)}")

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections.add(websocket)
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
            
            await redis_manager.publish("chat", json.dumps(message))
            logger.debug(f"Published message to Redis: {message}")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")
    finally:
        active_connections.remove(websocket)

@app.on_event("startup")
async def startup_event():
    try:
        await redis_manager.connect()
        # 간단한 Redis 작업 수행
        await redis_manager.redis.set("test_key", "test_value")
        value = await redis_manager.redis.get("test_key")
        logger.info(f"Redis test: {value}")
    except Exception as e:
        logger.error(f"Redis connection test failed: {str(e)}")
        
@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    logger.info("Closed Redis connection")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)