# Smart Content Delivery System
## Mini Project for Computer Networks (UE25CS243A)
## Deliverable 1

### __Problem Understanding & Architecture__
  * __Problem Statement:__
    * The problem asks us to implement multiple content servers and clients where the SDN controller dynamically selects or reroutes traffic toward suitable servers based on network conditions
    * This is done using low-level IPv4 sockets implemented in Python for communication between clients and servers, Ryu is used for the SDN part which controls the flow of packets across the network and it uses OpenFlow to dynamically program switches to modify flow tables / dynamically alter routing paths and DPI (Deep Packet Inspection), Mininet is used to simulate the network topology
  * __Objectives:__
    * __Define the desired topology using Mininet:__ in this case, 2 Clients, 2 Servers and 4 Switches connected in the simplest configuration (Diamond Topology) while retaining testing features like multiple paths, multiple servers and multiple clients to simulate a Content Delivery Network (CDN) in the simplest way
    *  __Implement Low-Level IPv4 Sockets:__ write low-level IPv4 TCP Sockets in Python using the `socket` library for reliable connection and communication between server and host, also implement concurrency by using multi-threaded client request handling via daemon threads, implement error handling by detecting timeouts and robust exception management and application-level message exchange using custom tokens in the payload
    *  __Write the Ryu SDN Flow Controller logic:__ for Deliverable 1 a simple controller logic has to be implemented (load balancing, monitoring, blocking and recovery are a part of Deliverable 2 according to the rubrics), in this case I will be implementing 2 paths, one high latency and one low latency, and use Deep Packet Inspection (DPI) to reroute packets through fast path (prioritization) once a certain token has been found in them, this is implemented by modifying OpenFlow Switch flow tables
    *  __Exhaustive Testing:__ keeping the end goal of building a Smart Content Delivery System in mind, this simple setup demonstrates the working of the background frameworks which are later on used to build it, this simple setup will be subjected to multiple test cases such as path failures, concurrency, timeouts and normal functioning, also calculate the RTT to demonstrate successful rerouting
  * __Architecture / Topology:__
    
    <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/97b11fb1-8c75-4558-be39-1c7453adaef0" />
  * __Software Components:__
    * __`topology.py`:__ Mininet Python script which has the network topology of the Clients, Servers, Switches and Links, in this case the Diamond Topology, and also link performance, one slow link (with 10ms delay) and one fast link (with 2ms delay)
    * __`client.py`:__ Python implementation of low-level IPv4 TCP Sockets using `socket` library to initiate connections, send HTTP/1.1 requests having custom tokens, calculate RTT, and handle exceptions (timeouts, connection refusals and errors)
    * __`server.py`:__ Python implementation of multi-threaded content server implemented using daemon threads and IPv4 TCP sockets to handle concurrent client requests, process HTTP requests, and manage various exceptions (timeouts, resets and errors)
    * __`simple_controller.py`:__ Ryu SDN Flow Controller script written in Python that handles OpenFlow `Packet-In` events, does Deep Packet Inspection (DPI) to detect custom tokens, and dynamically updates OpenFlow switch flow tables via `Flow-Mod` messages for rerouting
  * __Communication Flow and Expected Network Behavior:__
    * __TCP Handshake & Request Initiation:__ client initiates a TCP connection to the target server via a 3-way handshake (`SYN`, `SYN-ACK`, `ACK`), `SYN` reaches the ingress switch (`s1`), triggering a `Packet-In` message to the Ryu Flow Controller (using the default high-latency path via `s3`, 10ms delay), once handshake completes, the client sends the HTTP/1.1 request payload
      
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/893e171c-fb76-4815-9327-f45fc8fe742d" />
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/15213a5d-e825-47da-9e63-d041dbeb514f" />
    * __Deep Packet Inspection (DPI) & Token Detection:__ Ryu SDN Flow Controller intercepts the payload and does Deep Packet Inspection (DPI) on it to detect custom application level token

      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/83afdb5a-9169-4629-8bad-ef850639ee11" />
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/333e24b2-9653-4dc5-802f-fd984c0dbf51" />
    * __Dynamic rerouting:__ upon detecting the token, controller updates the OpenFlow Switch flow tables by releasing `Flow-Mod` messages, this dynamically reroutes flow away from the slow path to fast path (`s4` via `s2`, 2ms delay, low latency)

      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/6cb4a34a-c191-40a7-9151-e6504b76ae5d" />
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/5151e110-5b3d-4b2b-89f5-0e9218a4a30c" />
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/7adeae16-b83e-4bf6-9966-e7fb5720e8af" />
    * __Concurrency & RTT Calculation:__ server receives and processes multiple request concurrently using daemon threads, returning HTTP/1.1 responses, client logs timestamps when response arrives to compute the Round Trip Time (RTT)
    * __Expected Behavior:__ default traffic goes through high-latency route, traffic with token in payload triggers rerouting to low-latency route, exceptions are handled gracefully
