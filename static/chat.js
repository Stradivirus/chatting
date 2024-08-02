const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

const clientId = Date.now().toString();
let ws;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

// 도배 방지를 위한 변수들
let lastMessageTime = 0;
let messageCount = 0;
let lastMessages = [];
let isBanned = false;
let banTimer = null;
let messageCountTimer = null;

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
            displayWarning(message.message);
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
    const message = messageInput.value.trim();
    if (message && ws && ws.readyState === WebSocket.OPEN) {
        if (canSendMessage(message)) {
            console.log("Sending message:", message);
            ws.send(message);
            messageInput.value = '';
            updateMessageCount();
        }
    } else {
        console.log("Cannot send message. WebSocket state:", ws ? ws.readyState : "WebSocket not initialized");
    }
}

function canSendMessage(message) {
    const currentTime = Date.now();

    // 1. 메시지 전송 간격 제한 (0.5초)
    if (currentTime - lastMessageTime < 500) {
        displayWarning("메시지를 너무 빠르게 보내고 있습니다. 잠시 기다려주세요.");
        return false;
    }

    // 2. 연속 동일 메시지 감지
    if (lastMessages.length >= 2 && lastMessages.every(msg => msg === message)) {
        banUser("동일한 메시지를 연속으로 보냈습니다. 30초 동안 채팅이 금지됩니다.");
        return false;
    }

    // 3. 메시지 길이 제한 (30자)
    if (message.length > 30) {
        displayWarning("메시지가 너무 깁니다. 30자 이내로 작성해주세요.");
        return false;
    }

    // 6. 메시지 전송 속도 제한
    if (isBanned) {
        displayWarning("현재 채팅이 금지된 상태입니다.");
        return false;
    }

    lastMessageTime = currentTime;
    lastMessages.push(message);
    if (lastMessages.length > 3) {
        lastMessages.shift();
    }

    return true;
}

function updateMessageCount() {
    messageCount++;
    if (messageCount === 1) {
        messageCountTimer = setTimeout(() => {
            messageCount = 0;
        }, 5000);
    } else if (messageCount >= 8) {
        banUser("메시지를 너무 많이 보냈습니다. 30초 동안 채팅이 금지됩니다.");
    }
}

function banUser(reason) {
    isBanned = true;
    displayWarning(reason);
    if (banTimer) {
        clearTimeout(banTimer);
    }
    banTimer = setTimeout(() => {
        isBanned = false;
        displayWarning("채팅 금지가 해제되었습니다.");
    }, 30000);
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

function displayWarning(warningMessage) {
    const warningElement = document.createElement('div');
    warningElement.textContent = warningMessage;
    warningElement.classList.add('warning-message');
    chatMessages.appendChild(warningElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// DOM이 완전히 로드된 후 실행
document.addEventListener('DOMContentLoaded', function() {
    connectWebSocket();
});