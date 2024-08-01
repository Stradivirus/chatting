let ws;
let nickname = '';

function showNicknameModal() {
    document.getElementById('nickname-modal').style.display = 'block';
}

function setNickname(event) {
    event.preventDefault();
    nickname = document.getElementById('nickname-input').value.trim();
    if (nickname) {
        document.getElementById('nickname-modal').style.display = 'none';
        connectWebSocket();
    }
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws_url = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(ws_url);

    ws.onopen = function() {
        console.log("WebSocket 연결됨");
        ws.send(JSON.stringify({type: 'join', nickname: nickname}));
    };

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        const messages = document.getElementById('messages');
        messages.innerHTML += `<p>${data.nickname}: ${data.message}</p>`;
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
        ws.send(JSON.stringify({type: 'message', nickname: nickname, message: input.value}));
        input.value = '';
    }
}

document.getElementById('nickname-form').addEventListener('submit', setNickname);
document.getElementById('chat-form').addEventListener('submit', sendMessage);

showNicknameModal();