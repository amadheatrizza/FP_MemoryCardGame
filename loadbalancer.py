import socket
import threading

backend_servers = [("0.0.0.0", 8001), ("0.0.0.0", 8002), ("0.0.0.0", 8003)]
server_index = 0
lock = threading.Lock()

def forward(client_socket, server_address):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect(server_address)

        def forward_data(src, dst):
            try:
                while True:
                    data = src.recv(1024)
                    if not data:
                        break
                    dst.sendall(data)
            finally:
                src.close()
                dst.close()

        threading.Thread(target=forward_data, args=(client_socket, server_socket), daemon=True).start()
        threading.Thread(target=forward_data, args=(server_socket, client_socket), daemon=True).start()

    except Exception as e:
        print(f"Failed to forward to backend {server_address}: {e}")
        client_socket.close()

def handle_client(client_socket):
    global server_index
    with lock:
        server = backend_servers[server_index]
        server_index = (server_index + 1) % len(backend_servers)
    forward(client_socket, server)

def start_load_balancer(host='0.0.0.0', port=8888):
    balancer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    balancer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    balancer_socket.bind((host, port))
    balancer_socket.listen(100)
    print(f"[LOAD BALANCER] Listening on {host}:{port}")

    try:
        while True:
            client_socket, client_address = balancer_socket.accept()
            print(f"[NEW CONNECTION] {client_address}")
            threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()
    except KeyboardInterrupt:
        print("Shutting down load balancer.")
    finally:
        balancer_socket.close()

if __name__ == "__main__":
    start_load_balancer()
