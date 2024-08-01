const chatDiv = document.getElementById('chat');
const messageInput = document.getElementById('messageText');
const ws = new WebSocket('ws://' + window.location.host + '/ws');

ws.onmessage = function(event) {
    const message = document.createElement('div');
    message.textContent = event.data;
    chatDiv.appendChild(message);
    chatDiv.scrollTop = chatDiv.scrollHeight;
};

function sendMessage() {
    if (messageInput.value) {
        ws.send(messageInput.value);
        messageInput.value = '';
    }
}