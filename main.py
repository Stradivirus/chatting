from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from datetime import datetime
import json
from redis_manager import RedisManager

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
    try:
        while True:
            data = await websocket.receive_text()
            message = {
                "client_id": client_id,
                "message": data,
                "timestamp": datetime.now().isoformat()
            }
            
            # Redis에 메시지 발행
            await redis_manager.publish("chat", json.dumps(message))
            
            # 모든 연결된 클라이언트에게 메시지 브로드캐스트
            for connection in active_connections.values():
                await connection.send_json(message)
    except WebSocketDisconnect:
        del active_connections[client_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)