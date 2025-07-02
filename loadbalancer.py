import socket
import threading

backend_servers = [("localhost", 8001), ("localhost", 8002), ("localhost", 8003)]
server_index = 0
lock = threading.Lock()

def forward(client_socket, server_address):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect(server_address)

        def forward_data(src, dst, direction):
            try:
                while True:
                    data = src.recv(1024)
                    if not data:
                        break
                    dst.sendall(data)
            except (ConnectionResetError, ConnectionAbortedError) as e:
                print(f"[FORWARD ERROR] {direction} closed: {e}")
            except Exception as e:
                print(f"[FORWARD ERROR] Unknown: {e}")
            finally:
                try:
                    src.shutdown(socket.SHUT_RD)
                except:
                    pass
                try:
                    dst.shutdown(socket.SHUT_WR)
                except:
                    pass
                src.close()
                dst.close()

        threading.Thread(target=forward_data, args=(client_socket, server_socket, "client->server"), daemon=True).start()
        threading.Thread(target=forward_data, args=(server_socket, client_socket, "server->client"), daemon=True).start()

    except Exception as e:
        print(f"Failed to forward to backend {server_address}: {e}")
        client_socket.close()

def handle_client(client_socket):
    global server_index
    max_attempts = len(backend_servers)
    attempt = 0

    while attempt < max_attempts:
        with lock:
            server = backend_servers[server_index]
            server_index = (server_index + 1) % len(backend_servers)

        try:
            test_socket = socket.create_connection(server, timeout=1)
            test_socket.close()

            print(f"[FORWARD] Redirecting to active backend server {server}")
            forward(client_socket, server)
            return
        except Exception as e:
            print(f"[SKIP] Backend {server} unavailable: {e}")
            attempt += 1

    print("[ERROR] All backend servers unavailable.")
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
            print(f"[NEW CONNECTION] {client_address}")
            threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()
    except KeyboardInterrupt:
        print("Shutting down load balancer.")
    finally:
        balancer_socket.close()

if __name__ == "__main__":
    start_load_balancer()
