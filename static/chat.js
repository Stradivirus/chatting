var ws = new WebSocket("ws://" + window.location.host + "/ws");

ws.onmessage = function(event) {
    var messages = document.getElementById('messages')
    var message = document.createElement('p')
    var content = document.createTextNode(event.data)
    message.appendChild(content)
    messages.appendChild(message)
    messages.scrollTop = messages.scrollHeight;
};

function sendMessage(event) {
    var input = document.getElementById("messageText")
    if (input.value) {
        ws.send(input.value)
        input.value = ''
    }
    event.preventDefault()
}