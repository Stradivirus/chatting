const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const clientIdDisplay = document.getElementById('client-id-display');

const clientId = Date.now().toString();
let ws;

function displayClientId() {
    if (clientIdDisplay) {
        clientIdDisplay.textContent = `Your Client ID: ${clientId}`;
    } else {
        console.warn("Client ID display element not found");
    }
}

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${clientId}`;
    console.log("Connecting to WebSocket:", wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log("WebSocket connection established");
        sendButton.disabled = false;
        messageInput.disabled = false;
    };

    ws.onmessage = function(event) {
        console.log("Received message:", event.data);
        try {
            const message = JSON.parse(event.data);
            displayMessage(message);
        } catch (error) {
            console.error("Error parsing message:", error);
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
    if (!message || typeof message !== 'object' || !message.message) {
        console.error("Invalid message format:", message);
        return;
    }
    const messageElement = document.createElement('div');
    messageElement.textContent = `${message.client_id === clientId ? 'You' : message.client_id}: ${message.message}`;
    messageElement.classList.add('message');
    
    if (message.client_id === clientId) {
        messageElement.classList.add('user-message');
    }
    
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

document.addEventListener('DOMContentLoaded', function() {
    displayClientId();
    connectWebSocket();
});