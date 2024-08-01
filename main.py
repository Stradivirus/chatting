from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
import json

app = FastAPI()

app.mount("/", StaticFiles(directory="static", html=True), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections = []

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
                    'nickname': 'System',
                    'message': f"{data['nickname']}님이 입장하셨습니다."
                }))
            elif data['type'] == 'message':
                await manager.broadcast(json.dumps({
                    'nickname': data['nickname'],
                    'message': data['message']
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(json.dumps({
            'nickname': 'System',
            'message': "클라이언트가 연결을 종료했습니다."
        }))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)