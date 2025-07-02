import socket
import threading


BACKEND_SERVER = ("localhost", 8001)

def handle_request(client_socket):

    request_data = b""
    try:
        client_socket.settimeout(2.0) 
        while b'\r\n\r\n' not in request_data:
            chunk = client_socket.recv(1024)
            if not chunk:
                break  
            request_data += chunk
        
        if not request_data:
            print("[LB] Client connected but sent no data.")
            return

        print(f"[LB] Received request, forwarding to {BACKEND_SERVER}...")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.connect(BACKEND_SERVER)
            
            server_socket.sendall(request_data)
            
            response_data = b""
            while True:
                chunk = server_socket.recv(1024)
                if not chunk:
                    break 
                response_data += chunk
            
            if response_data:
                client_socket.sendall(response_data)
            
            print("[LB] Successfully forwarded response to client.")

    except socket.timeout:
        print("[LB ERROR] Timed out waiting for client request.")
    except Exception as e:
        print(f"[LB ERROR] An error occurred during forwarding: {e}")
    finally:
        client_socket.close()

def start_load_balancer(host='0.0.0.0', port=8888):
    balancer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    balancer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    balancer_socket.bind((host, port))
    balancer_socket.listen(100)
    print(f"[LOAD BALANCER] Listening on {host}:{port}")

    try:
        while True:
            client_socket, client_address = balancer_socket.accept()
            print(f"[NEW CONNECTION] from {client_address}")
            # Each incoming request is handled in its own short-lived thread.
            thread = threading.Thread(target=handle_request, args=(client_socket,), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\nShutting down load balancer.")
    finally:
        balancer_socket.close()

if __name__ == "__main__":
    start_load_balancer()