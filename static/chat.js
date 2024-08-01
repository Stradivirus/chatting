// 안전한 웹소켓 연결 (프로덕션 환경에서는 wss:// 사용)
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

const messages = document.getElementById('messages');
const messageText = document.getElementById("messageText");
const chatForm = document.getElementById("chat-form");

let username = localStorage.getItem('username') || prompt("채팅에 사용할 이름을 입력하세요:");
localStorage.setItem('username', username);

ws.onopen = function() {
    console.log("WebSocket 연결이 열렸습니다.");
    addSystemMessage("채팅방에 연결되었습니다.");
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    addMessage(data.username, data.message, data.username === username);
};

ws.onclose = function() {
    console.log("WebSocket 연결이 닫혔습니다.");
    addSystemMessage("채팅방 연결이 끊어졌습니다. 페이지를 새로고침해 주세요.");
};

ws.onerror = function(error) {
    console.error("WebSocket 오류:", error);
    addSystemMessage("오류가 발생했습니다. 콘솔을 확인해 주세요.");
};

function addMessage(username, message, isSelf) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', isSelf ? 'self' : 'other');
    messageElement.innerHTML = `
        <strong>${username}:</strong>
        <span>${message}</span>
    `;
    messages.appendChild(messageElement);
    messages.scrollTop = messages.scrollHeight;
}

function addSystemMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', 'system');
    messageElement.textContent = message;
    messages.appendChild(messageElement);
    messages.scrollTop = messages.scrollHeight;
}

function sendMessage(event) {
    event.preventDefault();
    if (messageText.value) {
        const message = {
            username: username,
            message: messageText.value
        };
        ws.send(JSON.stringify(message));
        messageText.value = '';
    }
}

chatForm.addEventListener('submit', sendMessage);