const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

let ws;
const clientId = Date.now().toString();

function connectWebSocket() {
    ws = new WebSocket(`ws://${window.location.host}/ws/${clientId}`);

    ws.onmessage = function(event) {
        const message = JSON.parse(event.data);
        displayMessage(message);
    };

    ws.onclose = function(event) {
        console.log("WebSocket is closed. Reconnecting...");
        setTimeout(connectWebSocket, 1000);
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
    };
}

connectWebSocket();

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
        messageInput.value = '';
    } else if (ws.readyState !== WebSocket.OPEN) {
        console.log("WebSocket is not open. Message not sent.");
    }
}

function displayMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.textContent = `${message.client_id}: ${message.message}`;
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}