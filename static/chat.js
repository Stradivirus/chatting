let ws;
let nickname = '';

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
    const host = window.location.host;
    ws = new WebSocket(`${protocol}//${host}/ws`);

    ws.onopen = function() {
        console.log("WebSocket 연결이 열렸습니다.");
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
        console.log("WebSocket 연결이 닫혔습니다.");
        setTimeout(connectWebSocket, 1000); // 1초 후 재연결 시도
    };

    ws.onerror = function(error) {
        console.error("WebSocket 오류:", error);
    };
}

function sendMessage(event) {
    event.preventDefault();
    var input = document.getElementById("messageText");
    if (input.value && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'message', nickname: nickname, message: input.value}));
        input.value = '';
    } else if (ws.readyState !== WebSocket.OPEN) {
        console.log("WebSocket이 연결되어 있지 않습니다. 재연결을 시도합니다.");
        connectWebSocket();
    }
}

document.getElementById('nickname-form').addEventListener('submit', setNickname);
document.getElementById('chat-form').addEventListener('submit', sendMessage);

showNicknameModal();