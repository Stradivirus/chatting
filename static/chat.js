const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

const clientId = Date.now().toString();
let ws;

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${clientId}`;
    console.log("Connecting to WebSocket:", wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log("WebSocket connection established");
        sendButton.disabled = false;
        messageInput.disabled = false;
        loadChatHistory();
    };

    ws.onmessage = function(event) {
        console.log("Received message:", event.data);
        const message = JSON.parse(event.data);
        if (message.error) {
            displayError(message.error);
        } else {
            displayMessage(message);
        }
    };

    ws.onclose = function(event) {
        console.log("WebSocket is closed. Attempting to reconnect...");
        sendButton.disabled = true;
        messageInput.disabled = true;
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
    };
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
    messageElement.textContent = `${message.client_id === clientId ? 'You' : 'Other'}: ${message.message}`;
    messageElement.classList.add('message');
    
    if (message.client_id === clientId) {
        messageElement.classList.add('user-message');
    } else {
        messageElement.classList.add('other-message');
    }
    
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Keep only the latest 20 messages
    while (chatMessages.children.length > 20) {
        chatMessages.removeChild(chatMessages.firstChild);
    }
}

function displayError(error) {
    const errorElement = document.createElement('div');
    errorElement.textContent = error;
    errorElement.classList.add('error-message');
    chatMessages.appendChild(errorElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    setTimeout(() => {
        chatMessages.removeChild(errorElement);
    }, 5000);
}

async function loadChatHistory() {
    try {
        const response = await fetch('/chat_history');
        const history = await response.json();
        chatMessages.innerHTML = '';
        history.forEach(displayMessage);
    } catch (error) {
        console.error("Failed to load chat history:", error);
    }
}

// DOM이 완전히 로드된 후 실행
document.addEventListener('DOMContentLoaded', function() {
    connectWebSocket();
});