const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

let ws;

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/user`;
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log("WebSocket connection established");
    };

    ws.onmessage = function(event) {
        const message = JSON.parse(event.data);
        displayMessage(message);
    };

    ws.onclose = function(event) {
        console.log("WebSocket is closed. Reconnecting...");
        setTimeout(connectWebSocket, 5000);  // 5초 후 재연결 시도
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
    };
}

sendButton.onclick = function() {
    sendMessage();
};

messageInput.onkeypress = function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
};

function sendMessage() {
    const message = messageInput.value;
    if (message && ws.readyState === WebSocket.OPEN) {
        ws.send(message);
        displayMessage({ message: message, is_user: true });
        messageInput.value = '';
    } else if (ws.readyState !== WebSocket.OPEN) {
        console.log("WebSocket is not open. Message not sent.");
    }
}

function displayMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.textContent = message.message;
    messageElement.classList.add('message');
    
    if (message.is_user) {
        messageElement.classList.add('user-message');
    }
    
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 페이지 로드 시 WebSocket 연결
connectWebSocket();