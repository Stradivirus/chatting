const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

const clientId = Date.now().toString();
let ws;
let isConnecting = false;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function connectWebSocket() {
    if (isConnecting) return;
    isConnecting = true;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${clientId}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log("WebSocket connection established");
        isConnecting = false;
        reconnectAttempts = 0;
        updateUIConnectionStatus(true);
    };

    ws.onmessage = function(event) {
        const message = JSON.parse(event.data);
        displayMessage(message);
    };

    ws.onclose = function(event) {
        console.log("WebSocket is closed. Attempting to reconnect...");
        isConnecting = false;
        updateUIConnectionStatus(false);
        if (reconnectAttempts < maxReconnectAttempts) {
            setTimeout(connectWebSocket, 5000 * Math.pow(2, reconnectAttempts));
            reconnectAttempts++;
        } else {
            console.error("Max reconnection attempts reached. Please refresh the page.");
        }
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
        isConnecting = false;
    };
}

function updateUIConnectionStatus(isConnected) {
    // 연결 상태에 따라 UI 업데이트 (선택적)
    sendButton.disabled = !isConnected;
    messageInput.disabled = !isConnected;
    if (isConnected) {
        sendButton.textContent = "전송";
    } else {
        sendButton.textContent = "연결 중...";
    }
}

sendButton.onclick = sendMessage;

messageInput.onkeypress = function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
};

function sendMessage() {
    const message = messageInput.value.trim();
    if (message && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(message);
        messageInput.value = '';
    } else if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.log("WebSocket is not open. Attempting to reconnect...");
        connectWebSocket();
    }
}

function displayMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.textContent = `${message.client_id === clientId ? 'You' : 'Other'}: ${message.message}`;
    messageElement.classList.add('message');
    
    if (message.client_id === clientId) {
        messageElement.classList.add('user-message');
    }
    
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 페이지 로드 시 WebSocket 연결
connectWebSocket();

// 주기적으로 연결 상태 확인 및 재연결 시도
setInterval(() => {
    if (!ws || ws.readyState === WebSocket.CLOSED) {
        connectWebSocket();
    }
}, 10000);