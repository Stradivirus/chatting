let ws;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws_url = `${protocol}//${host}/fastapi-service/ws`;
    ws = new WebSocket(ws_url);

    ws.onopen = function() {
        console.log("WebSocket 연결됨");
    };

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        const messages = document.getElementById('messages');
        messages.innerHTML += `<p>${data.message}</p>`;
        messages.scrollTop = messages.scrollHeight;
    };

    ws.onclose = function() {
        console.log("WebSocket 연결 끊김");
        setTimeout(connectWebSocket, 5000);  // 5초 후 재연결 시도
    };

    ws.onerror = function(error) {
        console.error("WebSocket 오류:", error);
    };
}

function sendMessage(event) {
    event.preventDefault();
    const input = document.getElementById("messageText");
    if (input.value && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({message: input.value}));
        input.value = '';
    }
}

document.getElementById('chat-form').addEventListener('submit', sendMessage);

connectWebSocket();