const chatMessages = document.getElementById('chat-messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');

const clientId = Date.now().toString();
const ws = new WebSocket(`ws://${window.location.host}/ws/${clientId}`);

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    displayMessage(message);
};

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
    if (message) {
        ws.send(message);
        messageInput.value = '';
    }
}

function displayMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.textContent = `${message.client_id}: ${message.message}`;
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}