from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import json
import logging
import asyncio
from redis_manager import RedisManager
from prometheus_fastapi_instrumentator import Instrumentator

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Prometheus 메트릭 설정
Instrumentator().instrument(app).expose(app)

# 정적 파일 서비스 설정
app.mount("/static", StaticFiles(directory="static"), name="static")

# Redis 매니저 및 연결 관리 변수 초기화
redis_manager = RedisManager()
active_connections = {}
message_history = {}
banned_users = set()

# 루트 경로 핸들러
@app.get("/")
async def get():
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content)

# 메시지 브로드캐스트 함수
async def broadcast_messages():
    await redis_manager.subscribe("chat")
    async for message in redis_manager.listen():
        await asyncio.gather(
            *[connection.send_text(json.dumps(message)) for connection in active_connections.values()],
            return_exceptions=True
        )
        logger.debug(f"Broadcasted message to all clients: {message}")

# 스팸 체크 함수
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

# WebSocket 엔드포인트
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    client_ip = websocket.client.host
    if not await redis_manager.is_allowed_connection(client_ip):
        await websocket.close(code=1008, reason="Connection not allowed")
        return

    redis_manager.increment_connection_count(client_ip)
    try:
        await websocket.accept()
        active_connections[client_id] = websocket
        logger.info(f"New client connected: {client_id} from IP: {client_ip}")
        
        # 최근 메시지 전송
        recent_messages = await redis_manager.get_recent_messages("chat")
        for msg in recent_messages:
            await websocket.send_text(json.dumps(msg))
        
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from {client_id}: {data}")
            
            if client_id in banned_users:
                warning = {
                    "type": "warning",
                    "message": "You are currently banned from sending messages."
                }
                await websocket.send_text(json.dumps(warning))
                continue

            is_spam = await check_spam(client_id, data)
            if is_spam:
                banned_users.add(client_id)
                warning = {
                    "type": "warning",
                    "message": "You have been banned for 30 seconds due to spamming."
                }
                await websocket.send_text(json.dumps(warning))
                asyncio.create_task(unban_user_after_delay(client_id, 30))
                continue

            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }
            await asyncio.gather(
                redis_manager.store_message("chat", json.dumps(message)),
                redis_manager.publish("chat", json.dumps(message))
            )
            logger.debug(f"Published and stored message to Redis: {message}")

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"Error in websocket connection: {str(e)}")
    finally:
        if client_id in active_connections:
            del active_connections[client_id]
        if client_id in message_history:
            del message_history[client_id]
        redis_manager.decrement_connection_count(client_ip)
        logger.info(f"Connection closed for client: {client_id}")

# 사용자 차단 해제 함수
async def unban_user_after_delay(client_id: str, delay: int):
    await asyncio.sleep(delay)
    banned_users.remove(client_id)

# 애플리케이션 시작 이벤트
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

# 애플리케이션 종료 이벤트
@app.on_event("shutdown")
async def shutdown_event():
    await redis_manager.close()
    logger.info("Closed Redis connection")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)