import hashlib
import time
import sqlite3
import json
import logging
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os
from flask import jsonify
from dotenv import load_dotenv


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecret'
socketio = SocketIO(app, cors_allowed_origins="*", logger=False, engineio_logger=False)


connected_users = {} 

def init_db():
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        try:
            c.execute("SELECT expires_at FROM offline_queue LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("DROP TABLE IF EXISTS offline_queue")
            c.execute("DROP TABLE IF EXISTS users")
            
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (pub_id TEXT PRIMARY KEY, token_hash TEXT, pub_key TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS offline_queue 
                     (msg_id TEXT PRIMARY KEY, target_id TEXT, payload TEXT, expires_at REAL)''')
        conn.commit()

init_db()






# Loading variables from the .env file
load_dotenv() 
ADMIN_SECRET_KEY = os.environ.get('ADMIN_SECRET_KEY', 'error_@12345678')

@app.route('/api/hidden/stats')
def admin_stats():
    # 1. Check for the secret key in the URL parameters
    provided_key = request.args.get('key')
    
    if not provided_key or provided_key != ADMIN_SECRET_KEY:
        # Return a generic 404 to pretend this page doesn't even exist if the key is wrong
        return "Not Found", 404
        
    try:
        with sqlite3.connect('notrace.db', timeout=10) as conn:
            c = conn.cursor()
            
            # Get total registered identities
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            
            # Get total queued offline messages
            c.execute("SELECT COUNT(*) FROM offline_queue")
            queued_msgs = c.fetchone()[0]
            
        # Get currently active connections
        online_users_count = len(connected_users)
        
        # Return clean JSON data
        return jsonify({
            "status": "success",
            "metrics": {
                "current_online_users": online_users_count,
                "total_registered_identities": total_users,
                "queued_offline_messages": queued_msgs
            }
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": "Failed to retrieve stats"}), 500









def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def clean_expired_messages():
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM offline_queue WHERE expires_at < ?", (time.time(),))
        conn.commit()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('check_availability')
def check_availability(data):
    desired_id = data.get('desired_id', '').lower()
    if len(desired_id) < 3 or len(desired_id) > 12 or not desired_id.isalnum():
        emit('availability_response', {'available': False, 'msg': 'Must be 3-12 alphanumeric chars.'})
        return
        
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE pub_id=?", (desired_id,))
        exists = c.fetchone() is not None
        
    emit('availability_response', {'available': not exists, 'id': desired_id})

@socketio.on('register')
def handle_register(data):
    pub_id = data.get('public_id')
    token = data.get('private_token')
    pub_key = data.get('public_key') 
    
    if not pub_id or not token: return
    token_hash = hash_token(token)
    pub_key_str = json.dumps(pub_key) if isinstance(pub_key, dict) else pub_key
    
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash FROM users WHERE pub_id=?", (pub_id,))
        row = c.fetchone()
        
        if not row:
            c.execute("INSERT OR IGNORE INTO users (pub_id, token_hash, pub_key) VALUES (?, ?, ?)", 
                      (pub_id, token_hash, pub_key_str))
        elif row[0] != token_hash:
            return 
        conn.commit()

    connected_users[pub_id] = request.sid
    emit('status_update', {'id': pub_id, 'status': 'online'}, broadcast=True)

@socketio.on('fetch_offline')
def fetch_offline(data):
    pub_id = data.get('public_id')
    token = data.get('private_token')
    clean_expired_messages() 
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash FROM users WHERE pub_id=?", (pub_id,))
        row = c.fetchone()
        if not row or row[0] != hash_token(token): return
        c.execute("SELECT msg_id, payload FROM offline_queue WHERE target_id=?", (pub_id,))
        offline_msgs = c.fetchall()
    if offline_msgs:
        parsed_msgs = [json.loads(row[1]) for row in offline_msgs]
        emit('receive_offline', parsed_msgs, room=request.sid)

@socketio.on('ack_offline')
def ack_offline(data):
    pub_id = data.get('public_id')
    token = data.get('private_token')
    msg_ids = data.get('msg_ids', [])
    if not msg_ids: return
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash FROM users WHERE pub_id=?", (pub_id,))
        row = c.fetchone()
        if not row or row[0] != hash_token(token): return
        c.executemany("DELETE FROM offline_queue WHERE msg_id=? AND target_id=?", [(m_id, pub_id) for m_id in msg_ids])
        conn.commit()

@socketio.on('destroy_identity')
def destroy_identity(data):
    pub_id = data.get('public_id')
    token = data.get('private_token')
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash FROM users WHERE pub_id=?", (pub_id,))
        row = c.fetchone()
        if row and row[0] == hash_token(token):
            c.execute("DELETE FROM users WHERE pub_id=?", (pub_id,))
            c.execute("DELETE FROM offline_queue WHERE target_id=?", (pub_id,))
            conn.commit()
    if pub_id in connected_users:
        del connected_users[pub_id]
        emit('status_update', {'id': pub_id, 'status': 'offline'}, broadcast=True)

@socketio.on('check_user')
def check_user(data):
    target = data.get('target_id')
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE pub_id=?", (target,))
        exists = c.fetchone() is not None
    emit('user_exists', {'target_id': target, 'exists': exists})

@socketio.on('get_key')
def get_key(data):
    target = data.get('target_id')
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT pub_key FROM users WHERE pub_id=?", (target,))
        row = c.fetchone()
    if row:
        key_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        emit('key_response', {'target_id': target, 'public_key': key_data})

@socketio.on('get_status')
def get_status(data):
    target = data.get('target_id')
    is_online = target in connected_users
    emit('status_update', {'id': target, 'status': 'online' if is_online else 'offline'})

@socketio.on('typing')
def handle_typing(data):
    target = data.get('target_id')
    if target in connected_users:
        emit('is_typing', {'sender_id': data.get('sender_id')}, room=connected_users[target])

@socketio.on('msg_delivered')
def handle_delivered(data):
    target = data.get('target_id')
    if target in connected_users:
        emit('chat_delivered', {'by': data.get('sender_id')}, room=connected_users[target])

@socketio.on('mark_seen')
def handle_seen(data):
    target = data.get('target_id')
    if target in connected_users:
        emit('chat_seen', {'by': data.get('sender_id')}, room=connected_users[target])

@socketio.on('delete_message')
def handle_delete(data):
    sender_id = data.get('sender_id')
    token = data.get('token')
    target_id = data.get('target_id')
    msg_id = data.get('msg_id')
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash FROM users WHERE pub_id=?", (sender_id,))
        row = c.fetchone()
        if not row or row[0] != hash_token(token): return
    payload = {'sender_id': sender_id, 'msg_id': msg_id, 'is_delete': True}
    if target_id in connected_users:
        emit('remote_delete', payload, room=connected_users[target_id])
    else:
        with sqlite3.connect('notrace.db', timeout=10) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO offline_queue (msg_id, target_id, payload, expires_at) VALUES (?, ?, ?, ?)", 
                      (f"del_{msg_id}", target_id, json.dumps(payload), time.time() + 604800))
            conn.commit()

@socketio.on('system_warning')
def handle_system_warning(data):
    sender_id = data.get('sender_id')
    target_id = data.get('target_id')
    if target_id in connected_users:
        emit('receive_warning', {'sender_id': sender_id, 'msg': '⚠️ App backgrounded (Possible Screenshot/Recording)'}, room=connected_users[target_id])

@socketio.on('send_message')
def handle_send(data):
    sender_id = data.get('sender_id')
    token = data.get('token')
    target_id = data.get('target_id')
    
    with sqlite3.connect('notrace.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT token_hash FROM users WHERE pub_id=?", (sender_id,))
        row = c.fetchone()
        if not row or row[0] != hash_token(token): return
        
    msg_id = data.get('msg_id')
    is_burn = data.get('burn', False)
    
    msg_payload = {
        'sender_id': sender_id, 
        'ciphertext': data.get('ciphertext'), 
        'timestamp': data.get('timestamp', int(time.time() * 1000)),
        'msg_id': msg_id,
        'burn': is_burn,
        'burnTimeout': data.get('burnTimeout', 60),
        'isFile': data.get('isFile', False),
        'fileName': data.get('fileName', '')
    }
    
    if target_id in connected_users:
        emit('receive_message', msg_payload, room=connected_users[target_id])
    else:
        ttl_seconds = 86400 if is_burn else 604800 
        expires_at = time.time() + ttl_seconds
        with sqlite3.connect('notrace.db', timeout=10) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO offline_queue (msg_id, target_id, payload, expires_at) VALUES (?, ?, ?, ?)", 
                      (msg_id, target_id, json.dumps(msg_payload), expires_at))
            conn.commit()

@socketio.on('disconnect')
def handle_disconnect():
    for pub_id, sid in list(connected_users.items()):
        if sid == request.sid:
            del connected_users[pub_id]
            emit('status_update', {'id': pub_id, 'status': 'offline'}, broadcast=True)
            break

if __name__ == '__main__':

    server_mode = False


    if server_mode:
        socketio.run(app)
    else:
        socketio.run(app, host='0.0.0.0', port=5004, debug=True)



    # socketio.run(app, host='0.0.0.0', port=5004, debug=True, ssl_context='adhoc')