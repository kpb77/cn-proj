# TCP Content Server

from socket import *
import sys
import threading
import os
import mimetypes
from urllib.parse import unquote

# folder that holds the files served by this server, any file placed in it can be requested by its name
CONTENT_DIR = 'content'

# size of the pieces a file is read from disk and sent in
CHUNK_SIZE = 1024 * 1024

# sends a small plain text response (errors)
def send_text(connectionSocket, status, body):
    body = body.encode('utf-8')

    # standard HTTP/1.1 response
    header = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    connectionSocket.sendall(header.encode('utf-8') + body)

# serves one client, runs in its own thread so many clients can be served at the same time
def handle_client(connectionSocket, addr):
    try:

        # stop waiting for clients that connect but never send a request
        connectionSocket.settimeout(15)

        # pulls data from network interface (reads TCP buffer stream of size 1024 bytes and decodes the binary stream via UTF-8)
        request = connectionSocket.recv(1024).decode('utf-8', errors='ignore')
        print(f"received request from {addr}:\n{request.strip()}")

        # request line looks like: GET /path HTTP/1.1
        parts = request.split()

        if len(parts) >= 2 and parts[0] == "GET":

            # requested file name, query string removed and %escapes decoded
            filename = unquote(parts[1].split('?')[0]).lstrip('/')

            # resolve the real location and make sure it stays inside the content folder (for security, and preventing access of other directories)
            base = os.path.realpath(CONTENT_DIR)
            full_path = os.path.realpath(os.path.join(base, filename))

            if full_path.startswith(base + os.sep) and os.path.isfile(full_path):
                file_size = os.path.getsize(full_path)

                # content type is guessed from the file extension, works for any kind of file
                content_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'

                header = (
                    "HTTP/1.1 200 OK\r\n"
                    f"Content-Type: {content_type}\r\n"
                    f"Content-Length: {file_size}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                )
                connectionSocket.sendall(header.encode('utf-8'))

                # streams the file piece by piece so big files do not have to fit in memory
                with open(full_path, 'rb') as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        connectionSocket.sendall(chunk)
                print(f"sent file '{filename}' ({file_size} bytes) to {addr}")
            else:
                send_text(connectionSocket, "404 Not Found", f"file '{filename}' not found on this server\n")
                print(f"file '{filename}' requested by {addr} not found")
        else:
            send_text(connectionSocket, "400 Bad Request", "bad request\n")

    # handle slow or broken clients without stopping the server
    except Exception as e:
        print(f"error with client {addr}: {e}")

    # closes client session
    finally:
        connectionSocket.close()
        print(f"closed connection with {addr}\n")

def run_server():
    serverPort = 8080

    # create the content folder if it does not exist yet
    os.makedirs(CONTENT_DIR, exist_ok=True)

    # initialize IPV4 TCP socket
    serverSocket = socket(AF_INET, SOCK_STREAM)

    # enable reuse of local socket addresses to prevent wait delays
    serverSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

    # binds socket to listen across all active interfaces
    serverSocket.bind(('', serverPort))

    # set OS backlog queue size as 10 connection requests
    serverSocket.listen(10)

    print(f"server listening on port 8080, serving files from '{CONTENT_DIR}/'\n")

    try:
        while True:

            # waits for TCP 3-way handshake completion, returns connection socket channel and client's address
            connectionSocket, addr = serverSocket.accept()
            print(f"accepted connection from {addr}")

            # every client request gets its own thread
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