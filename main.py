from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime
import json
import logging
import asyncio
from kafka_manager import KafkaManager
from redis_manager import RedisManager
import uuid

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

redis_manager = RedisManager()
kafka_manager = KafkaManager(topic_retention_minutes=5)  # 5분 후 토픽 삭제
active_connections = {}

@app.on_event("startup")
async def startup_event():
    try:
        await redis_manager.connect()
        await kafka_manager.connect_producer()
        await kafka_manager.connect_admin()
        asyncio.create_task(broadcast_messages())
        asyncio.create_task(kafka_manager.kafka_message_handler())
        logger.info("Starting consume_messages task")
        asyncio.create_task(kafka_manager.start_consuming())
        await kafka_manager.start_background_tasks()
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    await kafka_manager.close()

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
        await kafka_manager.add_to_message_queue(message)
        logger.debug(f"Broadcasted message and added to Kafka queue: {message}")

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
        
        while True:
            try:
                data = await websocket.receive_text()
                logger.debug(f"Received message from {client_id}: {data}")
                
                message = {
                    "id": str(uuid.uuid4()),
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
        logger.info(f"Connection closed for client: {client_id}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
