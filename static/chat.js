const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

const clientId = Date.now().toString();
let ws;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
let isBlocked = false;
let blockTimer;

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${clientId}`;
    console.log("Connecting to WebSocket:", wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log("WebSocket connection established");
        sendButton.disabled = false;
        messageInput.disabled = false;
        reconnectAttempts = 0;
    };

    ws.onmessage = function(event) {
        console.log("Received message:", event.data);
        const message = JSON.parse(event.data);
        if (message.type === 'warning') {
            displayWarning(message.message, message.remainingTime);
        } else {
            displayMessage(message);
        }
    };

    ws.onclose = function(event) {
        console.log("WebSocket is closed. Attempting to reconnect...");
        sendButton.disabled = true;
        messageInput.disabled = true;
        reconnectWithBackoff();
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
    };
}

function reconnectWithBackoff() {
    if (reconnectAttempts >= maxReconnectAttempts) {
        console.log("Max reconnection attempts reached. Please refresh the page.");
        return;
    }
    
    const backoffTime = Math.pow(2, reconnectAttempts) * 1000;
    console.log(`Attempting to reconnect in ${backoffTime / 1000} seconds...`);
    
    setTimeout(() => {
        reconnectAttempts++;
        connectWebSocket();
    }, backoffTime);
}

sendButton.onclick = sendMessage;

messageInput.onkeypress = function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
};

function sendMessage() {
    if (isBlocked) {
        console.log("Cannot send message. User is currently blocked.");
        return;
    }
    
    const message = messageInput.value.trim();
    if (message && ws && ws.readyState === WebSocket.OPEN) {
        console.log("Sending message:", message);
        ws.send(message);
        messageInput.value = '';
    } else {
        console.log("Cannot send message. WebSocket state:", ws ? ws.readyState : "WebSocket not initialized");
    }
}

function displayMessage(message) {
    console.log("Displaying message:", message);
    const messageElement = document.createElement('div');
    messageElement.textContent = message.message;
    messageElement.classList.add('message');

    if (message.client_id === clientId) {
        messageElement.classList.add('user-message');
    } else {
        messageElement.classList.add('other-message');
    }

    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function displayWarning(warningMessage, remainingTime) {
    messageInput.placeholder = warningMessage;
    messageInput.style.color = 'red';
    isBlocked = true;
    
    if (blockTimer) {
        clearInterval(blockTimer);
    }
    
    blockTimer = setInterval(() => {
        remainingTime--;
        if (remainingTime <= 0) {
            clearInterval(blockTimer);
            messageInput.placeholder = '';
            messageInput.style.color = '';
            isBlocked = false;
        } else {
            messageInput.placeholder = `도배 방지: ${remainingTime}초 동안 채팅이 금지됩니다.`;
        }
    }, 1000);
}

// DOM이 완전히 로드된 후 실행
document.addEventListener('DOMContentLoaded', function() {
    connectWebSocket();
});