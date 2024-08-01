from fastapi import FastAPI, WebSocket, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
import secrets
import logging
from typing import List
import os
import json

app = FastAPI()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영 환경에서는 특정 도메인으로 제한해야 합니다
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 키 보안 설정
API_KEY = os.environ.get("API_KEY", "your-secret-api-key")
api_key_header = APIKeyHeader(name="X-API-Key")

def get_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API Key"
        )
    return api_key

# Static 파일을 서빙하기 위한 설정
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# WebSocket 연결을 관리하기 위한 클래스
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            data = json.loads(data)
            if data['type'] == 'join':
                await manager.broadcast(json.dumps({
                    'type': 'system',
                    'nickname': 'System',
                    'message': f"{data['nickname']}님이 입장하셨습니다."
                }))
            elif data['type'] == 'message':
                await manager.broadcast(json.dumps({
                    'type': 'message',
                    'nickname': data['nickname'],
                    'message': data['message']
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({
            'type': 'system',
            'nickname': 'System',
            'message': f"클라이언트가 연결을 종료했습니다."
        }))

# 보안이 적용된 새로운 API 엔드포인트 예시
@app.get("/secure-endpoint", dependencies=[Depends(get_api_key)])
async def secure_endpoint():
    return {"message": "This is a secure endpoint"}

# 에러 핸들링
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {"detail": exc.detail}, exc.status_code

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)