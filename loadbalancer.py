import socket
import threading
import json
import hashlib
from urllib.parse import parse_qs

# A list of all your backend servers.
BACKEND_SERVERS = [
    ("localhost", 8001),
    ("localhost", 8002),
    ("localhost", 8003)
]

# Session affinity tracking
room_to_server = {}  # Maps room_id to server address
player_to_room = {}  # Maps player_id to room_id
session_lock = threading.Lock()

def extract_session_info(request_data):
    """Extract room_id or player_id from the request to determine session affinity"""
    try:
        # Find the JSON body in the HTTP request
        if b'\r\n\r\n' in request_data:
            headers, body = request_data.split(b'\r\n\r\n', 1)
            if body:
                try:
                    json_data = json.loads(body.decode())
                    
                    # Check for room_id first
                    if 'room_id' in json_data:
                        room_id = json_data['room_id']
                        player_id = json_data.get('player_id')
                        return room_id, player_id
                    
                    # Then check for player_id
                    if 'player_id' in json_data:
                        player_id = json_data['player_id']
                        with session_lock:
                            room_id = player_to_room.get(player_id)
                        if room_id:
                            return room_id, player_id
                        
                except json.JSONDecodeError:
                    # Try to parse as form data if JSON fails
                    try:
                        params = parse_qs(body.decode())
                        if 'room_id' in params:
                            room_id = params['room_id'][0]
                            player_id = params.get('player_id', [None])[0]
                            return room_id, player_id
                        if 'player_id' in params:
                            player_id = params['player_id'][0]
                            with session_lock:
                                room_id = player_to_room.get(player_id)
                            if room_id:
                                return room_id, player_id
                    except:
                        pass
    except Exception as e:
        print(f"Error extracting session info: {e}")
    return None, None

def get_server_for_room(room_id):
    """Get the server address for a given room_id"""
    with session_lock:
        return room_to_server.get(room_id)

def assign_server_to_room(room_id, server_address):
    """Assign a room to a specific server"""
    with session_lock:
        room_to_server[room_id] = server_address

def assign_player_to_room(player_id, room_id):
    """Keep track of which room a player is in"""
    with session_lock:
        player_to_room[player_id] = room_id

def get_next_server():
    """Simple round-robin server selection"""
    servers = BACKEND_SERVERS.copy()
    while True:
        for server in servers:
            yield server

server_rotation = get_next_server()

def handle_request(client_socket):
    """
    Handles a client request by forwarding it to the appropriate backend server.
    Uses session affinity when possible, falls back to round-robin.
    """
    try:
        # 1. Read the full request from the client.
        request_data = b""
        try:
            client_socket.settimeout(2.0)
            while b'\r\n\r\n' not in request_data:
                chunk = client_socket.recv(4096)
                if not chunk:
                    return  # Client disconnected prematurely
                request_data += chunk
            
            # Read remaining data if Content-Length specifies more
            headers = request_data.split(b'\r\n\r\n')[0]
            if b'Content-Length:' in headers:
                content_length = int(headers.split(b'Content-Length:')[1].split(b'\r\n')[0].strip())
                body_start = request_data.find(b'\r\n\r\n') + 4
                current_body_length = len(request_data) - body_start
                while current_body_length < content_length:
                    chunk = client_socket.recv(4096)
                    if not chunk:
                        break
                    request_data += chunk
                    current_body_length = len(request_data) - body_start
        except socket.timeout:
            print("[LB ERROR] Timed out waiting for client request.")
            return
        except Exception as e:
            print(f"[LB ERROR] Error reading request: {e}")
            return

        if not request_data:
            return

        # 2. Extract session information for sticky routing
        room_id, player_id = extract_session_info(request_data)
        server_address = None
        
        if room_id:
            server_address = get_server_for_room(room_id)
            if server_address:
                print(f"[LB] Using session affinity for room {room_id} -> {server_address}")
        
        # 3. If no server found by room_id, try player_id
        if not server_address and player_id:
            with session_lock:
                room_id = player_to_room.get(player_id)
                if room_id:
                    server_address = room_to_server.get(room_id)
                    if server_address:
                        print(f"[LB] Using player {player_id} affinity to room {room_id} -> {server_address}")

        # 4. If still no server, use round-robin
        if not server_address:
            server_address = next(server_rotation)
            print(f"[LB] No session info, using round-robin to {server_address}")

        # 5. Forward the request
        try:
            print(f"[LB] Forwarding request to {server_address}...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.settimeout(5.0)
                server_socket.connect(server_address)
                server_socket.sendall(request_data)
                
                response_data = b""
                while True:
                    chunk = server_socket.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                
                if response_data:
                    # If this was a create_room or join_room request, update our mappings
                    try:
                        response_str = response_data.decode()
                        if '\r\n\r\n' in response_str:
                            headers, body = response_str.split('\r\n\r\n', 1)
                            if body:
                                response_json = json.loads(body)
                                if response_json.get('success'):
                                    if 'room_id' in response_json and 'player_id' in response_json:
                                        new_room_id = response_json['room_id']
                                        new_player_id = response_json['player_id']
                                        assign_server_to_room(new_room_id, server_address)
                                        assign_player_to_room(new_player_id, new_room_id)
                                        print(f"[LB] Associated room {new_room_id} and player {new_player_id} with {server_address}")
                    except Exception as e:
                        print(f"[LB] Error processing response: {e}")
                    
                    client_socket.sendall(response_data)
                    return
        except (socket.timeout, ConnectionRefusedError) as e:
            print(f"[LB WARNING] Backend {server_address} is unavailable ({e}). Trying next...")
        except Exception as e:
            print(f"[LB ERROR] An unexpected error occurred with {server_address}: {e}")

        # 6. If we get here, the server failed - try another one
        print("[LB] Primary server failed, trying others...")
        for backup_server in BACKEND_SERVERS:
            if backup_server == server_address:
                continue
                
            try:
                print(f"[LB] Trying backup server {backup_server}...")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                    server_socket.settimeout(5.0)
                    server_socket.connect(backup_server)
                    server_socket.sendall(request_data)
                    
                    response_data = b""
                    while True:
                        chunk = server_socket.recv(4096)
                        if not chunk:
                            break
                        response_data += chunk
                    
                    if response_data:
                        client_socket.sendall(response_data)
                        return
            except Exception as e:
                print(f"[LB] Backup server {backup_server} failed: {e}")

        # 7. If all servers failed
        print("[LB ERROR] All backend servers failed to respond.")
        error_response = b"HTTP/1.1 503 Service Unavailable\r\n\r\n"
        client_socket.sendall(error_response)

    finally:
        client_socket.close()

def start_load_balancer(host='0.0.0.0', port=8888):
    balancer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    balancer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    balancer_socket.bind((host, port))
    balancer_socket.listen(100)
    print(f"[LOAD BALANCER] Listening on {host}:{port}")
    print(f"[LOAD BALANCER] Forwarding traffic to: {BACKEND_SERVERS}")
    print(f"[LOAD BALANCER] Using session affinity for game sessions")

    try:
        while True:
            client_socket, client_address = balancer_socket.accept()
            thread = threading.Thread(target=handle_request, args=(client_socket,), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\nShutting down load balancer.")
    finally:
        balancer_socket.close()

if __name__ == "__main__":
    start_load_balancer()