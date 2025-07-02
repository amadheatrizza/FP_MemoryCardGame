import socket
import threading

# A list of all your backend servers.
BACKEND_SERVERS = [
    ("localhost", 8001),
    ("localhost", 8002),
    ("localhost", 8003)
]

# Shared resources for round-robin selection
current_server_index = 0
lock = threading.Lock()

def handle_request(client_socket):
    """
    Handles a client request by forwarding it to a backend server.
    This function now correctly closes the client socket in all scenarios.
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
            if not request_data:
                return
        except socket.timeout:
            print("[LB ERROR] Timed out waiting for initial client request.")
            return # Exit, which will trigger the 'finally' block to close the socket.

        # 2. Try to forward the request to a server using round-robin and failover.
        max_attempts = len(BACKEND_SERVERS)
        for _ in range(max_attempts):
            with lock:
                global current_server_index
                server_address = BACKEND_SERVERS[current_server_index]
                current_server_index = (current_server_index + 1) % len(BACKEND_SERVERS)

            try:
                print(f"[LB] Attempting to forward request to {server_address}...")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                    server_socket.settimeout(1.0)
                    server_socket.connect(server_address)
                    
                    server_socket.sendall(request_data)
                    
                    response_data = b""
                    while True:
                        chunk = server_socket.recv(4096)
                        if not chunk:
                            break
                        response_data += chunk
                    
                    if response_data:
                        client_socket.sendall(response_data)
                    
                    print(f"[LB] Successfully processed request via {server_address}.")
                    return # Success! Exit, 'finally' block will run.

            except (socket.timeout, ConnectionRefusedError) as e:
                print(f"[LB WARNING] Backend {server_address} is unavailable ({e}). Trying next...")
                continue # Try the next server.
                
            except Exception as e:
                print(f"[LB ERROR] An unexpected error occurred with {server_address}: {e}")
                break

        # 3. If the loop finishes, all servers were unavailable. Inform the client.
        print("[LB ERROR] All backend servers failed to respond.")
        error_response = b"HTTP/1.1 503 Service Unavailable\r\n\r\n"
        client_socket.sendall(error_response)

    finally:
        # 4. This 'finally' block GUARANTEES the connection to the client is always closed,
        # no matter what happened in the 'try' block. This prevents the client from freezing.
        print(f"[LB] Closing client connection.")
        client_socket.close()


def start_load_balancer(host='0.0.0.0', port=8888):
    balancer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    balancer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    balancer_socket.bind((host, port))
    balancer_socket.listen(100)
    print(f"[LOAD BALANCER] Listening on {host}:{port}")
    print(f"[LOAD BALANCER] Forwarding traffic to: {BACKEND_SERVERS}")

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