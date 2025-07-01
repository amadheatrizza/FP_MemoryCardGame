from socket import *
import socket
import time
import sys
import logging
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from http import GameServer

server = GameServer()

def ProcessTheClient(connection,address):
        rcv=""
        while True:
            try:
                data = connection.recv(1024)
                if data:
                    d = data.decode()
                    rcv=rcv+d
                    if '\r\n\r\n' in rcv:
                        response = server.proses(rcv, connection)
                        print(response)
                        connection.sendall(response)
                        rcv=""
                        connection.close()
                        return
                else:
                    break
            except OSError as e:
                pass
        connection.close()
        return

def main():
    the_clients = []
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    my_socket.bind(('0.0.0.0', 8002))
    my_socket.listen(1)

    with ThreadPoolExecutor(20) as executor:
        while True:
                connection, client_address = my_socket.accept()
                p = executor.submit(ProcessTheClient, connection, client_address)
                the_clients.append(p)
                jumlah = ['x' for i in the_clients if i.running()==True]
                print(jumlah)

if __name__=="__main__":
    main()
