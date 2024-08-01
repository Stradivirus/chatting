let ws;

function connectWebSocket() {
    const host = window.location.host;  // 이는 LoadBalancer의 IP 또는 도메인이 될 것입니다.
    const ws_url = `ws://${host}/ws`;
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