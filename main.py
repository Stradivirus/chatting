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
active_connections = {}

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

async def broadcast_messages():
    await redis_manager.subscribe("chat")
    async for message in redis_manager.listen():
        for connection in active_connections.values():
            await connection.send_json(message)
            logger.debug(f"Broadcasted message to client: {message}")

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

            await redis_manager.publish("chat", json.dumps(message))
            logger.debug(f"Published message to Redis: {message}")
    except WebSocketDisconnect:
        del active_connections[client_id]
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")

@app.on_event("startup")
async def startup_event():
    await redis_manager.connect()
    logger.info("Connected to Redis")
    asyncio.create_task(broadcast_messages())
    logger.info("Started message broadcasting task")

@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    logger.info("Closed Redis connection")

if name == "main":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)