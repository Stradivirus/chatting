from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import json
import logging
import asyncio
from redis_manager import RedisManager
from chatting.kafka_count import KafkaManager

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

kafka_manager = KafkaManager()
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
        logger.debug(f"Broadcasted message to all clients: {message}")

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
    client_ip = websocket.client.host
    
    if not await redis_manager.is_allowed_connection(client_ip):
        await websocket.close(code=1008, reason="Connection not allowed")
        return

    try:
        await websocket.accept()
        redis_manager.increment_connection_count(client_ip)
        active_connections[client_id] = websocket
        logger.info(f"New client connected: {client_id} from IP: {client_ip}")
        
        # Update Kafka connection count
        await kafka_manager.update_connection_count(1)
        
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
    finally:
        if client_id in active_connections:
            del active_connections[client_id]
        if client_id in message_history:
            del message_history[client_id]
        redis_manager.decrement_connection_count(client_ip)
        # Update Kafka connection count
        await kafka_manager.update_connection_count(-1)
        logger.info(f"Connection closed for client: {client_id}")

async def broadcast_connection_count(count):
    count_message = json.dumps({"type": "connection_count", "count": count})
    await asyncio.gather(
        *[connection.send_text(count_message) for connection in active_connections.values()],
        return_exceptions=True
    )

@app.on_event("startup")
async def startup_event():
    try:
        await redis_manager.connect()
        logger.info("Connected to Redis")
        await kafka_manager.connect()
        logger.info("Connected to Kafka")
        # Kafka 토픽 생성 (없는 경우)
        await kafka_manager.create_topic("connection_count")
        asyncio.create_task(broadcast_messages())
        asyncio.create_task(kafka_manager.consume_count_updates(broadcast_connection_count))
        await kafka_manager.start_count_updates()
        logger.info("Started message broadcasting and Kafka count updates")
    except Exception as e:
        logger.error(f"Failed to start up properly: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    kafka_manager.stop_count_updates()
    await kafka_manager.disconnect()
    logger.info("Closed Redis and Kafka connections")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)