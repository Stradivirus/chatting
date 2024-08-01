from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from redis_manager import RedisManager
from kafka_manager import KafkaManager
from datetime import datetime
import json
import os

app = FastAPI()

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Redis and Kafka managers
redis_manager = RedisManager()
kafka_manager = KafkaManager()

# WebSocket connections
active_connections = []

@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Publish to Redis
            await redis_manager.publish("chat", json.dumps(message))
            
            # Produce to Kafka
            topic = f"chat-{datetime.now().strftime('%Y-%m-%d')}"
            await kafka_manager.produce(topic, message)
            
            # Broadcast to all clients
            await broadcast(message)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    finally:
        await redis_manager.close()
        await kafka_manager.close()

async def broadcast(message: dict):
    for connection in active_connections:
        await connection.send_json(message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)