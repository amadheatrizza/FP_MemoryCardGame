import socket
import threading
import json
import time
import random
from typing import List, Tuple, Dict
import logging
from concurrent.futures import ProcessPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ServerHealth:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.is_healthy = True
        self.connection_count = 0
        self.last_check = time.time()
        self.response_time = 0.0
    
    def check_health(self) -> bool:
        try:
            start_time = time.time()
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(2.0)
            result = test_socket.connect_ex((self.host, self.port))
            test_socket.close()
            
            self.response_time = time.time() - start_time
            self.is_healthy = (result == 0)
            self.last_check = time.time()
            
            return self.is_healthy
        except Exception as e:
            logger.error(f"Health check failed for {self.host}:{self.port} - {e}")
            self.is_healthy = False
            return False

class LoadBalancer:
    def __init__(self, lb_host='localhost', lb_port=8080):
        self.lb_host = lb_host
        self.lb_port = lb_port
        self.servers: List[ServerHealth] = []
        self.running = False
        self.executor = ProcessPoolExecutor(max_workers=8)
        self.health_check_interval = 10  # seconds
        
        # Load balancing strategies
        self.strategies = {
            'round_robin': self._round_robin,
            'least_connections': self._least_connections,
            'weighted_response_time': self._weighted_response_time
        }
        self.current_strategy = 'least_connections'
        self.round_robin_index = 0
    
    def add_server(self, host: str, port: int):
        server_health = ServerHealth(host, port)
        self.servers.append(server_health)
        logger.info(f"Added server {host}:{port} to load balancer")
    
    def remove_server(self, host: str, port: int):
        self.servers = [s for s in self.servers if not (s.host == host and s.port == port)]
        logger.info(f"Removed server {host}:{port} from load balancer")
    
    def get_healthy_servers(self) -> List[ServerHealth]:
        return [s for s in self.servers if s.is_healthy]
    
    def _round_robin(self) -> ServerHealth:
        healthy_servers = self.get_healthy_servers()
        if not healthy_servers:
            return None
        
        server = healthy_servers[self.round_robin_index % len(healthy_servers)]
        self.round_robin_index += 1
        return server
    
    def _least_connections(self) -> ServerHealth:
        healthy_servers = self.get_healthy_servers()
        if not healthy_servers:
            return None
        
        return min(healthy_servers, key=lambda s: s.connection_count)
    
    def _weighted_response_time(self) -> ServerHealth:
        healthy_servers = self.get_healthy_servers()
        if not healthy_servers:
            return None
        
        # Choose server with best response time and lowest connections
        def score(server):
            return server.response_time + (server.connection_count * 0.1)
        
        return min(healthy_servers, key=score)
    
    def select_server(self) -> ServerHealth:
        strategy_func = self.strategies.get(self.current_strategy, self._least_connections)
        return strategy_func()
    
    def proxy_connection(self, client_socket, client_address):
        selected_server = self.select_server()
        
        if not selected_server:
            logger.error("No healthy servers available")
            error_response = {
                "success": False,
                "message": "No game servers available. Please try again later."
            }
            try:
                client_socket.send(json.dumps(error_response).encode())
            except:
                pass
            client_socket.close()
            return
        
        try:
            # Connect to selected game server
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.connect((selected_server.host, selected_server.port))
            selected_server.connection_count += 1
            
            logger.info(f"Proxying client {client_address} to server {selected_server.host}:{selected_server.port}")
            
            # Start bidirectional data forwarding
            def forward_data(source, destination, direction):
                try:
                    while True:
                        data = source.recv(4096)
                        if not data:
                            break
                        destination.send(data)
                except Exception as e:
                    logger.debug(f"Connection closed ({direction}): {e}")
                finally:
                    try:
                        source.close()
                        destination.close()
                    except:
                        pass
            
            # Create threads for bidirectional forwarding
            client_to_server = threading.Thread(
                target=forward_data,
                args=(client_socket, server_socket, "client->server")
            )
            server_to_client = threading.Thread(
                target=forward_data,
                args=(server_socket, client_socket, "server->client")
            )
            
            client_to_server.daemon = True
            server_to_client.daemon = True
            
            client_to_server.start()
            server_to_client.start()
            
            # Wait for either thread to finish
            client_to_server.join()
            server_to_client.join()
            
        except Exception as e:
            logger.error(f"Error proxying connection: {e}")
        finally:
            selected_server.connection_count = max(0, selected_server.connection_count - 1)
            try:
                client_socket.close()
                server_socket.close()
            except:
                pass
    
    def health_check_loop(self):
        while self.running:
            for server in self.servers:
                try:
                    was_healthy = server.is_healthy
                    is_now_healthy = server.check_health()
                    
                    if was_healthy != is_now_healthy:
                        status = "healthy" if is_now_healthy else "unhealthy"
                        logger.info(f"Server {server.host}:{server.port} is now {status}")
                        
                except Exception as e:
                    logger.error(f"Health check error for {server.host}:{server.port}: {e}")
            
            time.sleep(self.health_check_interval)
    
    def get_stats(self) -> Dict:
        healthy_count = len(self.get_healthy_servers())
        total_connections = sum(s.connection_count for s in self.servers)
        
        return {
            "total_servers": len(self.servers),
            "healthy_servers": healthy_count,
            "total_connections": total_connections,
            "current_strategy": self.current_strategy,
            "servers": [
                {
                    "host": s.host,
                    "port": s.port,
                    "healthy": s.is_healthy,
                    "connections": s.connection_count,
                    "response_time": s.response_time
                } for s in self.servers
            ]
        }
    
    def handle_admin_request(self, client_socket, client_address):
        try:
            data = client_socket.recv(1024).decode().strip()
            if data.startswith("GET /stats"):
                stats = self.get_stats()
                response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{json.dumps(stats, indent=2)}"
                client_socket.send(response.encode())
            elif data.startswith("GET /health"):
                health_status = {"status": "healthy" if self.get_healthy_servers() else "unhealthy"}
                response = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{json.dumps(health_status)}"
                client_socket.send(response.encode())
            else:
                response = "HTTP/1.1 404 Not Found\r\n\r\nEndpoint not found"
                client_socket.send(response.encode())
        except Exception as e:
            logger.error(f"Error handling admin request: {e}")
        finally:
            client_socket.close()
    
    def start_admin_server(self, admin_port=9090):
        def admin_server():
            admin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            admin_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            admin_socket.bind((self.lb_host, admin_port))
            admin_socket.listen(5)
            
            logger.info(f"Admin server started on {self.lb_host}:{admin_port}")
            
            while self.running:
                try:
                    client_socket, client_address = admin_socket.accept()
                    admin_thread = threading.Thread(
                        target=self.handle_admin_request,
                        args=(client_socket, client_address)
                    )
                    admin_thread.daemon = True
                    admin_thread.start()
                except Exception as e:
                    if self.running:
                        logger.error(f"Admin server error: {e}")
            
            admin_socket.close()
        
        admin_thread = threading.Thread(target=admin_server)
        admin_thread.daemon = True
        admin_thread.start()
    
    def start(self, admin_port=9090):
        if not self.servers:
            logger.error("No servers configured. Add servers before starting.")
            return
        
        self.running = True
        
        # Start health check thread
        health_thread = threading.Thread(target=self.health_check_loop)
        health_thread.daemon = True
        health_thread.start()
        
        # Start admin server
        self.start_admin_server(admin_port)
        
        # Start main load balancer
        lb_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lb_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lb_socket.bind((self.lb_host, self.lb_port))
        lb_socket.listen(10)
        
        logger.info(f"Load Balancer started on {self.lb_host}:{self.lb_port}")
        logger.info(f"Admin interface available at http://{self.lb_host}:{admin_port}/stats")
        
        try:
            while self.running:
                client_socket, client_address = lb_socket.accept()
                
                # Handle connection in thread pool
                self.executor.submit(self.proxy_connection, client_socket, client_address)
                
        except KeyboardInterrupt:
            logger.info("Load balancer shutting down...")
        finally:
            self.running = False
            lb_socket.close()
            self.executor.shutdown(wait=True)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Memory Card Game Load Balancer')
    parser.add_argument('--host', default='localhost', help='Load balancer host')
    parser.add_argument('--port', type=int, default=8080, help='Load balancer port')
    parser.add_argument('--admin-port', type=int, default=9090, help='Admin interface port')
    parser.add_argument('--servers', nargs='+', 
                       help='Game servers in format host:port (e.g., localhost:8888 localhost:8889)')
    parser.add_argument('--strategy', choices=['round_robin', 'least_connections', 'weighted_response_time'],
                       default='least_connections', help='Load balancing strategy')
    
    args = parser.parse_args()
    
    # Create load balancer
    lb = LoadBalancer(args.host, args.port)
    lb.current_strategy = args.strategy
    
    # Add servers
    if args.servers:
        for server_str in args.servers:
            try:
                host, port = server_str.split(':')
                lb.add_server(host, int(port))
            except ValueError:
                logger.error(f"Invalid server format: {server_str}. Use host:port")
                return
    else:
        # Default servers
        lb.add_server('localhost', 8888)
        lb.add_server('localhost', 8889)
    
    # Start load balancer
    lb.start(args.admin_port)

if __name__ == "__main__":
    main()