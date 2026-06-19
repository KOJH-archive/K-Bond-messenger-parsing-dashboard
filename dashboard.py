from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kbond_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    if not data: return "No data", 400
    
    # 핑 메시지는 처리하지 않고 응답만 함
    if data.get("type") == "ping":
        return "pong", 200
        
    socketio.emit('new_message', data)
    return "OK", 200

if __name__ == '__main__':
    print("Dashboard server starting at http://localhost:5000")
    socketio.run(app, port=5000, debug=True, allow_unsafe_werkzeug=True)
