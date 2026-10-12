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
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/b9bffaf1-0052-4035-b005-29074cfa130d" />
      <img width="4945" height="3172" alt="image" src="https://github.com/user-attachments/assets/d9da7722-906f-4af6-a388-cc6e7df074de" />
    * __Concurrency & RTT Calculation:__ server receives and processes multiple request concurrently using daemon threads, returning HTTP/1.1 responses, client logs timestamps when response arrives to compute the Round Trip Time (RTT)
    * __Expected Behavior:__ default traffic goes through high-latency route, traffic with token in payload triggers rerouting to low-latency route, exceptions are handled gracefully
### __Low-level IPv4 TCP Socket Implementation__
  * The low-level IPv4 TCP Sockets are implemented in Python using the `socket` library, this ensures reliable connection and communication between server and host, concurrency (handling multiple requests) is implemented on the server side by multi-threading using daemon threads
  * Check out `client.py` and `server.py` to see the implementation, abundant comments are included in the implementation to explain how the code works
### __Mininet and SDN Implementation__
  * The topology is implemented using Mininet written in Python, here we are implementing the Diamond Topology with 2 clients, 2 servers and 4 switches, there are 2 paths a packet can take viz a high latency and low latency path, routing is decided by Ryu SDN Flow Controller based on certain network conditions, the implementation can be seen in `topology.py`, which includes abundant comments to explain how the code works
  * The SDN is implemented in `simple_controller.py` which is a Ryu SDN Flow Controller script written in Python, it handles OpenFlow Packet-In events, does Deep Packet Inspection (DPI) to detect custom tokens, and dynamically updates OpenFlow switch flow tables via Flow-Mod messages for rerouting when the token is detected in the payload, abundant comments are included in the implementation to explain how the controller logic works
### __Socket–SDN Integration__
  * When a TCP connection is established by a client with the target server after the 3-way TCP handshake, a HTTP/1.1 request is sent out to the ingress switch, which then triggers Deep Packet Inspection (DPI) in the request payload to search for a certain pre-defined token (in this case kpb77)
  * Upon detection of the defined token in the payload, `Flow-Mod` messages are sent to the switches in the path meant to be taken by this high priority packet installing the routing path in them
  * In this implementation, upon detection of the token `kpb77` in the payload, the Ryu SDN Flow Controller sends a `Flow-Mod` message to the switches in the low latency path (default is high latency) and installs the routing flow in them causing this certain high priority packet to take the low latency path, the HTTP/1.1 response from server to client also takes the same but reverse path
  * Check out the __Communication Flow and Expected Network Behavior__ section in __Problem Understanding and Architecture__ for a detailed overview and `simple_controller.py` for seeing how the DPI and rerouting is handled
### __Initial Testing and Demo__
  * __Pre requisite steps:__ follow the steps laid out in `README.md` present in the root directory of this repository, then clone this repository by typing
    ```
    git clone https://github.com/kpb77/cn-proj
    ```
  * __Step 0:__
    * This step must be done every time whenever a new bunch of unrelated tests has to be done, this is very important, run this command in a normal terminal window every time you have to perform a new bunch of tests
      ```
      sudo mn -c
      ```
  * __Setting things up:__
    * Open 6 terminal windows and change the working directory to `cn-proj/deliverable1`, and follow these steps in a strict sequential manner:
      * In the first terminal window (`term1`), type this
        ```
        source ~/ryu/bin/activate
        ```
        and this
        
        ```
        ryu-manager simple_controller.py
        ```
        this activates the Ryu virtual environment and starts the Ryu SND Flow Controller script `simple_controller.py`
      * In the second terminal window (`term2`) type this
        ```
        sudo python3 topology.py
        ```
        this starts up the Mininet topology defined in `topology.py`

        now we start the 2 servers h2 and h3 and start logging by these commands in the Mininet prompt
        ```
        h2 python3 -u server.py > /tmp/h2.log 2>&1 &
        ```
        
        ```
        h3 python3 -u server.py > /tmp/h3.log 2>&1 &
        ```
        
      * In the third terminal window (`term3`) type this
        ```
        tail -f /tmp/h2.log
        ```
        this opens up the dynamic/live server logs for h2
      * In the fourth terminal window (`term4`) type this
        ```
        tail -f /tmp/h3.log
        ```
        this opens up the dynamic/live server logs for h3
      * In the fifth terminal window (`term5`) type this
        ```
        sudo tcpdump -i s3-eth1 -n tcp port 8080
        ```
        this is used to monitor the live TCP network traffic on the slow path (via s3)
      * And in the sixth terminal window (`term6`) type this
        ```
        sudo tcpdump -i s2-eth1 -n tcp port 8080
        ```
        this is used to monitor the live TCP network traffic on the fast path (via s2)
      * __Testcase 1:__ Check if both servers are listening
        * For this, open up `term3` and `term4`, you will see something like this
          <img width="1487" height="513" alt="image" src="https://github.com/user-attachments/assets/d2d34aa8-637d-4476-872a-84f79358deb7" />
      * __Testcase 2:__ Check if topology is running and controller can program switches
        * Run these commands in the Mininet prompt in `term2`
          ```
          nodes
          ```

          ```
          net
          ```

          ```
          pingall
          ```

          ```
          h1 ping -c 5 h2
          ```
        * This is the desired output
          <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/c8b18643-7e2c-48c8-9909-a4a6a3d1f8c6" />

          And in `term1` (controller logs), this will be seen
          <img width="753" height="321" alt="image" src="https://github.com/user-attachments/assets/0b165341-8329-4d04-93ce-871b19f87a45" />
       * __Testcase 3:__ Default path used (token not in payload)
         * Run these commands in the Mininet prompt in `term2`
           ```
           h1 python3 client.py 10.0.0.2 notthetoken
           ```

           ```
           h4 python3 client.py 10.0.0.2 notthetoken
           ```
         * The output should look something like this
           in `term2`
           <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/332cfbdb-b015-4e4f-819a-ceae2088f3fb" />

           in `term1`
           <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/006048fd-561d-4f36-acb1-6f5a247dfd04" />

           and in `term4`
           <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/3cb4daf6-9ebf-41a9-9993-a4e5b32845fd" />

           this is the TCP traffic shown in `term6`
           <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/d8e046fe-a95f-449b-b5ac-80def7b6744e" />

           from this we can clearly see that by default and when there is no token in the payload, the slow path is being utilized
        * __Testcase 4:__ Fast path used (token in payload)
          * Run these commands in the Mininet prompt in `term2`, here we are passing the token `kpb77` as the parameter and also check the flow tables of the switches involved in fast path 
            ```
            h1 python3 client.py 10.0.0.2 kpb77
            ```

            ```
            sh ovs-ofctl -O OpenFlow13 dump-flows s1
            ```

            ```
            sh ovs-ofctl -O OpenFlow13 dump-flows s2
            ```

            ```
            sh ovs-ofctl -O OpenFlow13 dump-flows s3
            ```

            this is the desired output seen in `term2`
            <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/10c58f83-cd50-46c0-a00b-560694c4a9f5" />

            here, we can clearly see the routing tables being changed

            this is the output in `term1`
            <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/93457252-e391-4c30-b0ca-6ece844f0a84" />

            token is detected

            this is the server log seen in `term4`
            <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/543270ad-7adf-47a0-b1d7-49298157684a" />

            this is the TCP traffic across s3 shown in `term6`
            <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/5c8c852b-b767-4958-8209-9c3d22878063" />

            and this is the TCP traffic across s2 shown in `term5`
            <img width="1911" height="1078" alt="image" src="https://github.com/user-attachments/assets/33d6dab2-c2ea-4800-8dbb-9e6531bb8243" />

            this shows that the 3-way handshake and the HTTP/1.1 request happen via the slow path, the server response happens via the fast path, which means my assumptions were wrong that the payload traverses through the fast path
       * __Testcase 5:__ Concurrency
         Execute the following in `term2`
         ```
         h1 for i in 1 2 3 4 5; do python3 client.py 10.0.0.2 & done; wait
         ```
         this sends 5 requests from h1 to h2

         this is the output in `term2`
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/fff614a4-9a34-4940-a112-24eb0eed95c5" />

         this is the output in `term1`
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/271c6709-2958-4986-9d4d-165c44127e4d" />

         this is the output in `term4`
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/633ff910-8cb9-4297-ac90-ee48511cdab1" />

         this is the output in `term5`
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/1b6274ab-f07e-4625-876c-8afa8883c8a3" />

         this is the output in `term6`
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/e134a69e-5dae-4bf2-8f0b-957f3bcc4c5a" />

         concurrency is clearly showcased here
       * __Testcase 6:__ Idle Client Timeout
         execute this command in `term2`
         ```
         h1 python3 -c "import socket,time; s=socket.socket(); s.connect(('10.0.0.2',8080)); time.sleep(8)" &
         ```

         ```
         h4 python3 client.py 10.0.0.2 notthetoken
         ```

         this is the ouput
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/af662239-2d6e-42f5-a81a-2728167a2cc3" />
       * __Testcase 7:__ Malformed Request
         execute this command in `term2`
         ```
         h1 python3 -c "import socket; s=socket.socket(); s.connect(('10.0.0.2',8080)); s.send(b'HELLO\r\n\r\n'); print(s.recv(4096).decode())"
         ```

         this should give a 400 bad request
         <img width="1917" height="1078" alt="image" src="https://github.com/user-attachments/assets/50ae259d-1ab1-4aac-82c9-ba8b75ff7358" />
       * __Testcase 8:__ Connection Refused (Client Side error handling)
         ```
         h3 pkill -f server.py
         ```

         ```
         h1 python3 client.py 10.0.0.3 notthetoken
         ```
         we get this standard message
         <img width="1916" height="1077" alt="image" src="https://github.com/user-attachments/assets/b3bd62d3-53f6-4297-9389-eb6e88fe4dab" />



          


