// DOM 요소 선택
const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

// 클라이언트 ID 생성 및 웹소켓 관련 변수 초기화
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
let banCountdown = 0;
let messageCountTimer = null;

// 웹소켓 연결 함수
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
        const data = JSON.parse(event.data);
        if (data.type === 'warning') {
            displayWarning(data.message);
        } else {
            displayMessage(data);
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

// 재연결 함수 (지수 백오프 사용)
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

// 메시지 전송 이벤트 리스너
sendButton.onclick = sendMessage;

messageInput.onkeypress = function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
};

// 메시지 전송 함수
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

// 메시지 전송 가능 여부 확인 함수
function canSendMessage(message) {
    const currentTime = Date.now();

    if (isBanned) {
        displayWarning(`채팅이 금지되었습니다. ${banCountdown}초 후에 다시 시도해주세요.`);
        return false;
    }

    if (currentTime - lastMessageTime < 500) {
        displayWarning("메시지를 너무 빠르게 보내고 있습니다. 잠시 기다려주세요.");
        return false;
    }

    if (lastMessages.length >= 5 && lastMessages.every(msg => msg === message)) {
        banUser("동일한 메시지를 연속으로 보냈습니다.");
        return false;
    }

    if (message.length > 30) {
        displayWarning("메시지가 너무 깁니다. 30자 이내로 작성해주세요.");
        return false;
    }

    lastMessageTime = currentTime;
    lastMessages.push(message);
    if (lastMessages.length > 5) {
        lastMessages.shift();
    }

    return true;
}

// 메시지 카운트 업데이트 함수
function updateMessageCount() {
    messageCount++;
    if (messageCount === 1) {
        if (messageCountTimer) {
            clearTimeout(messageCountTimer);
        }
        messageCountTimer = setTimeout(() => {
            messageCount = 0;
        }, 5000);
    } else if (messageCount >= 8) {
        banUser("메시지를 너무 많이 보냈습니다.");
    }
}

// 사용자 차단 함수
function banUser(reason) {
    isBanned = true;
    banCountdown = 30;
    displayWarning(`${reason} ${banCountdown}초 동안 채팅이 금지됩니다.`);
    if (banTimer) {
        clearInterval(banTimer);
    }
    banTimer = setInterval(() => {
        banCountdown--;
        if (banCountdown <= 0) {
            clearInterval(banTimer);
            isBanned = false;
            removeWarning();
        } else {
            updateBanWarning();
        }
    }, 1000);
}

// 차단 경고 업데이트 함수
function updateBanWarning() {
    const warningElement = document.querySelector('.warning-message');
    if (warningElement) {
        warningElement.textContent = `채팅이 금지되었습니다. ${banCountdown}초 후에 다시 시도해주세요.`;
    }
}

// 메시지 표시 함수
function displayMessage(data) {
    console.log("Displaying message:", data);
    const messageElement = document.createElement('div');
    messageElement.textContent = `${data.client_id}: ${data.message}`;
    messageElement.classList.add('message');

    if (data.client_id === clientId) {
        messageElement.classList.add('user-message');
    } else {
        messageElement.classList.add('other-message');
    }

    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 경고 메시지 표시 함수
function displayWarning(warningMessage) {
    removeWarning(); // 기존 경고 메시지 제거
    const warningElement = document.createElement('div');
    warningElement.textContent = warningMessage;
    warningElement.classList.add('warning-message');
    chatMessages.appendChild(warningElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 경고 메시지 제거 함수
function removeWarning() {
    const existingWarning = document.querySelector('.warning-message');
    if (existingWarning) {
        existingWarning.remove();
    }
}

// DOM 로드 완료 시 웹소켓 연결
document.addEventListener('DOMContentLoaded', function() {
    connectWebSocket();
});