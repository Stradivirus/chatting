const chatDiv = document.getElementById('chat');
const messageInput = document.getElementById('messageText');
const sendButton = document.getElementById('sendButton');
let ws;

function connectWebSocket() {
    ws = new WebSocket('ws://' + window.location.host + '/fastapi-service/ws');

    ws.onopen = function() {
        console.log('WebSocket 연결 성공');
        sendButton.disabled = false;
    };

    ws.onmessage = function(event) {
        const message = document.createElement('div');
        message.textContent = event.data;
        chatDiv.appendChild(message);
        chatDiv.scrollTop = chatDiv.scrollHeight;
    };

    ws.onclose = function() {
        console.log('WebSocket 연결 끊김. 재연결 시도...');
        sendButton.disabled = true;
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = function(error) {
        console.error('WebSocket 오류:', error);
    };
}

function sendMessage() {
    if (messageInput.value && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(messageInput.value);
        messageInput.value = '';
    }
}

sendButton.addEventListener('click', sendMessage);

messageInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

connectWebSocket();