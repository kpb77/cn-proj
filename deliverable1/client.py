# TCP Client

from socket import *
import sys
import time

def run_client():

    # extract server destination IP from command line argument, default to h2 (10.0.0.2) in case IP not passed
    serverName = sys.argv[1] if len(sys.argv) > 1 else '10.0.0.2'

    serverPort = 8080

    # initialize IPv4 TCP socket
    clientSocket = socket(AF_INET, SOCK_STREAM)
    
    # record start time to calculate RTT
    start_time = time.time()
    
    try:

        # initiate TCP 3-way handshake with server
        clientSocket.connect((serverName, serverPort))

        # standard HTTP/1.1 GET request (almost)
        message = f"GET /PES1UG25CS255 HTTP/1.1\r\nHost: {serverName}\r\n\r\n"
        
        # encode text string and send it across socket
        clientSocket.send(message.encode('utf-8'))

        # read response from server, max size of which is 4096 bytes
        modifiedMessage = clientSocket.recv(4096)
        
        # calculate RTT
        elapsed = time.time() - start_time
        
        # print performance metrics with server response
        print(f"\nRTT: {elapsed:.4f}s and response from server: ")
        print(modifiedMessage.decode('utf-8', errors='ignore'))

    # handle routing failures or timeouts gracefully
    except Exception as e:
        print(f"connection failed: {e}")
        
    # socket closed
    finally:
        clientSocket.close()

if __name__ == '__main__':
    run_client()