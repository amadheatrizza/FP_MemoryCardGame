from socket import *
import socket
import time
import sys
import logging
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from https import GameServer

server = GameServer()

def ProcessTheClient(connection, address):
    print(f"[SERVER] Connection from {address}")
    rcv = ""
    while True:
        try:
            data = connection.recv(1024)
            if data:
                d = data.decode()
                rcv += d
                print("[SERVER] Received:", repr(rcv))

                if '\r\n\r\n' in rcv:
                    response = server.proses(rcv, connection)
                    print("[SERVER] Response:", response)
                    connection.sendall(response)
                    rcv = ""
                    connection.close()
                    return
            else:
                break
        except OSError as e:
            print("[SERVER] Error:", e)
    connection.close()

def Server():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    the_clients = []

    my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    my_socket.bind(('0.0.0.0', port))
    my_socket.listen(1)

    print(f"[SERVER] Listening on port {port}")

    with ThreadPoolExecutor(20) as executor:
        while True:
            connection, client_address = my_socket.accept()
            p = executor.submit(ProcessTheClient, connection, client_address)
            the_clients.append(p)
            jumlah = ['x' for i in the_clients if i.running()==True]
            print(jumlah)

def main():
    Server()

if __name__=="__main__":
    main()
