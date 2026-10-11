# TCP Content Server

from socket import *
import sys
import threading

# serves one client, runs in its own thread so many clients can be served at the same time
def handle_client(connectionSocket, addr):
    try:

        # stop waiting for clients that connect but never send a request
        connectionSocket.settimeout(5)

        # pulls data from network interface (reads TCP buffer stream of size 1024 bytes and decodes the binary stream via UTF-8)
        request = connectionSocket.recv(1024).decode('utf-8', errors='ignore')
        print(f"received request from {addr}:\n{request.strip()}")

        # request line looks like: GET /path HTTP/1.1
        parts = request.split()

        # response body and status depend on whether the request is valid
        if len(parts) >= 2 and parts[0] == "GET":
            status = "200 OK"
            body = "yoyoyo this is the server speaking yo, PES1UG25CS255\n"
        else:
            status = "400 Bad Request"
            body = "bad request\n"

        # standard HTTP/1.1 response
        response = (
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{body}"
        )

        # encodes and sends response
        connectionSocket.sendall(response.encode('utf-8'))

    # handle slow or broken clients without stopping the server
    except Exception as e:
        print(f"error with client {addr}: {e}")

    # closes client session
    finally:
        connectionSocket.close()
        print(f"closed connection with {addr}\n")

def run_server():
    serverPort = 8080

    # initialize IPV4 TCP socket
    serverSocket = socket(AF_INET, SOCK_STREAM)

    # enable reuse of local socket addresses to prevent wait delays
    serverSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

    # binds socket to listen across all active interfaces
    serverSocket.bind(('', serverPort))

    # set OS backlog queue size as 5 connection requests
    serverSocket.listen(5)

    print("server listening on port 8080\n")

    try:
        while True:

            # waits for TCP 3-way handshake completion, returns connection socket channel and client's address
            connectionSocket, addr = serverSocket.accept()
            print(f"accepted connection from {addr}")

            # every client gets its own thread
            t = threading.Thread(target=handle_client, args=(connectionSocket, addr))
            t.daemon = True
            t.start()

    # handle Ctrl + C gracefully
    except KeyboardInterrupt:
        print("\nstopping server")

    # socket closed
    finally:
        serverSocket.close()

if __name__ == '__main__':
    run_server()
