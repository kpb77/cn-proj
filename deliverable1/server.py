# TCP Content Server

from socket import *
import sys

def run_server():
    serverPort = 8080

    # initialize IPV4 TCP socket
    serverSocket = socket(AF_INET, SOCK_STREAM)

    # enable reuse of local socket addresses to prevent wait delays
    serverSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

    # binds socket to listen across all active interfaces
    serverSocket.bind(('', serverPort))

    # set OS backlog queue size as 1 connection request
    serverSocket.listen(1)

    print("server listening on port 8080\n")

    try:
        while True:

            # waits for TCP 3-way handshake conpletion, returns connection socket channel and client's address
            connectionSocket, addr = serverSocket.accept()
            print(f"accepted connection from {addr}")

            # pulls data from network interface (reads TCP buffer stream of size 1024 bytes and decodes the binary stream via UTF-8)
            request = connectionSocket.recv(1024).decode('utf-8', errors='ignore')
            print(f"received request:\n{request.strip()}")

            # response to send back to client
            body = "yoyoyo this is the server speaking yo, PES1UG25CS255\n"
            
            # standard HTTP/1.1 response
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n"
                "\r\n"
                f"{body}"
            )
            
            # encodes and sends response
            connectionSocket.sendall(response.encode('utf-8'))

            # closes client session
            connectionSocket.close()
            print(f"closed connection with {addr}\n")
    
    # handle Ctrl + C gracefully
    except KeyboardInterrupt:
        print("\nstopping server")

    # socket closed
    finally:
        serverSocket.close()

if __name__ == '__main__':
    run_server()