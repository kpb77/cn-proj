# TCP Client

from socket import *
import sys
import time
import os

def run_client():

    # requested file from 1st command line argument, default is kpb77.txt
    path = sys.argv[1] if len(sys.argv) > 1 else 'kpb77.txt'

    # server destination IP from 2nd command line argument, default is the virtual IP of the service (the controller picks the mirror)
    serverName = sys.argv[2] if len(sys.argv) > 2 else '10.0.0.5'

    serverPort = 8080

    # initialize IPv4 TCP socket
    clientSocket = socket(AF_INET, SOCK_STREAM)

    # give up after 15 seconds without data instead of hanging forever
    clientSocket.settimeout(15)

    # record start time to calculate RTT
    start_time = time.time()

    try:

        # initiate TCP 3-way handshake with server
        clientSocket.connect((serverName, serverPort))

        # standard HTTP/1.1 GET request (almost)
        message = f"GET /{path} HTTP/1.1\r\nHost: {serverName}\r\n\r\n"

        # encode text string and send it across socket
        clientSocket.send(message.encode('utf-8'))

        # read the whole response, the server closes the connection after the last byte
        response = b""
        while True:
            chunk = clientSocket.recv(65536)
            if not chunk:
                break
            response += chunk

        # calculate RTT (time until the complete response has arrived)
        elapsed = time.time() - start_time

        # split the response into header and body
        header, _, body = response.partition(b"\r\n\r\n")
        header_text = header.decode('utf-8', errors='ignore')
        status_line = header_text.split("\r\n")[0]

        # print performance metrics with server response
        throughput = len(body) * 8 / elapsed / 1e6
        print(f"\nRTT: {elapsed:.4f}s | {len(body)} bytes | throughput: {throughput:.2f} Mbps")
        print(f"response from server: {status_line}")

        # files are saved on successful download (200 OK)
        if status_line.endswith("200 OK"):
            name = "received_" + os.path.basename(path)
            with open(name, 'wb') as f:
                f.write(body)
            print(f"saved file as {name}")
        else:
            print(body.decode('utf-8', errors='ignore'))

    # handle routing failures or timeouts gracefully
    except Exception as e:
        print(f"connection failed: {e}")

    # socket closed
    finally:
        clientSocket.close()

if __name__ == '__main__':
    run_client()