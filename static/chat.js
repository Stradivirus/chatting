let ws;
let nickname = '';
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function showNicknameModal() {
    document.getElementById('nickname-modal').style.display = 'block';
}

function hideNicknameModal() {
    document.getElementById('nickname-modal').style.display = 'none';
}

function setNickname(event) {
    event.preventDefault();
    nickname = document.getElementById('nickname-input').value.trim();
    if (nickname) {
        hideNicknameModal();
        connectWebSocket();
    }
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = '34.85.7.99';  // LoadBalancer의 External-IP
    const port = 80; // 서비스가 노출된 포트
    const ws_url = `${protocol}//${host}:${port}/ws`;
    console.log("Attempting to connect to:", ws_url);
    
    ws = new WebSocket(ws_url);

    ws.onopen = function() {
        console.log("WebSocket 연결이 열렸습니다.");
        reconnectAttempts = 0;
        ws.send(JSON.stringify({type: 'join', nickname: nickname}));
    };

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        var messages = document.getElementById('messages');
        var message = document.createElement('p');
        var content = document.createTextNode(`${data.nickname}: ${data.message}`);
        message.appendChild(content);
        messages.appendChild(message);
        messages.scrollTop = messages.scrollHeight;
    };

    ws.onclose = function(event) {
        console.log("WebSocket 연결이 닫혔습니다.", event);
        ws = null;
        if (reconnectAttempts < maxReconnectAttempts) {
            console.log(`재연결 시도 ${reconnectAttempts + 1}/${maxReconnectAttempts}`);
            setTimeout(connectWebSocket, 1000 * Math.pow(2, reconnectAttempts));
            reconnectAttempts++;
        } else {
            console.log("최대 재연결 시도 횟수를 초과했습니다.");
        }
    };

    ws.onerror = function(error) {
        console.error("WebSocket 오류:", error);
        ws = null;
    };
}

function sendMessage(event) {
    event.preventDefault();
    var input = document.getElementById("messageText");
    if (input.value && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'message', nickname: nickname, message: input.value}));
        input.value = '';
    } else if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.log("WebSocket이 연결되어 있지 않습니다. 재연결을 시도합니다.");
        connectWebSocket();
    }
}

document.getElementById('nickname-form').addEventListener('submit', setNickname);
document.getElementById('chat-form').addEventListener('submit', sendMessage);

showNicknameModal();