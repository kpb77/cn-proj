# Smart Content Delivery System
## Mini Project for Computer Networks (UE25CS243A)
## Deliverable 2

### __Problem Understanding & Architecture__
  * __Problem Statement:__
    * The problem asks us to implement multiple content servers and clients where the SDN controller dynamically selects or reroutes traffic toward suitable servers based on network conditions
    * Deliverable 1 built the foundation (sockets, topology, token based rerouting), Deliverable 2 turns it into a complete Smart Content Delivery System: the controller now selects the server for every request (proximity, health and load), monitors the network, reroutes around link failures, recovers when failed components come back, and the servers deliver actual files
    * The same stack is used, low-level IPv4 TCP sockets in Python for the application, Ryu with OpenFlow 1.3 for the SDN control, Mininet for the network, and Linux `tc` (netem) to emulate the geographic latency between clients and mirrors
  * __Objectives:__
    * __Complete Application Functionality:__ clients request real files (any file type) from a single virtual IP, the controller transparently picks the right mirror server, the server streams the file back, and the client reports the response time (RTT) and throughput
    * __Proximity Anycast Server Selection:__ the 2 servers are mirrors of the same content, one in India (`h2`) and one in Europe (`h3`), the 2 clients are in Singapore (`h1`) and Canada (`h4`), every client is served by the mirror with the lowest latency to it, as long as that mirror is healthy and not overloaded
    * __Primary / Backup Paths:__ the fast link (via `s2`) is the primary path and is used by default, the slow link (via `s3`) is only a backup that is used while the primary path is down
    * __Dynamic SDN Functionality:__ routing, prioritization (token DPI), load balancing, monitoring, rerouting and recovery are all done by the controller by modifying OpenFlow flow tables at runtime
    * __Challenging Scenarios / Robustness:__ server failure, link failure, server overload and their recovery are simulated and handled without restarting anything
    * __Performance Evaluation:__ response time and throughput are measured under multiple conditions, and the proposed (dynamic) controller is compared against a static baseline controller which uses a fixed server and a fixed path
  * __Software Components:__
    * __`topology.py`:__ Mininet Python script with the Diamond Topology (clients, servers, switches, links, one fast link with 2ms delay and one slow link with 10ms delay), added `add_location_latency()` which uses `tc` (`prio` + `netem`) on `h2` and `h3` to delay the replies going to each client by the latency of that client-server pair
    * __`client.py`:__ Python implementation of low-level IPv4 TCP Sockets, sends the HTTP/1.1 request for a file, takes responses until the server closes the connection (big files arrive completely), calculates RTT and throughput, and saves the received file
    * __`server.py`:__ multi-threaded content server (using daemon threads), serves any file from the `content` folder (type detected using `mimetypes`), streams it in 1 MB chunks, returns `404` for missing files and for paths trying to leave the folder (a crucial security feature), `400` for malformed requests
    * __`smart_controller.py`:__ Ryu SDN Flow Controller script, some features implemented are proxy ARP, virtual IP with per-connection NAT, health probes, proximity & health & load based server selection, port statistics monitoring, link and server failure handling, flow flushing for rerouting and recovery, and a `static` baseline mode for benchmarking improvements
  * __Communication Flow and Expected Network Behavior:__
    * __ARP Resolution:__ the clients send an ARP Request for the virtual IP `10.0.0.5`, the request reaches `s1` and the table-miss rule sends it to the controller, which answers it itself with the virtual MAC of the proxy server
    * __TCP Handshake & Server Selection:__ the client sends the `SYN` to the virtual IP, `s1` has no rule for it and sends a `Packet-In` to the controller, the controller selects the server, first removing servers that are down (health), then taking the one with the lowest latency to this client (proximity), skipping it if it already has `MAX_SERVER_LOAD` active connections (load), then it selects the path (fast, or slow if the fast path is down)
    * __Flow Installation (NAT):__ the controller installs per-connection `Flow-Mod` rules on every switch of the chosen path for both directions, `s1` rewrites the destination of requests from the virtual IP to the real mirror (DNAT), `s4` rewrites the source of replies from the real mirror back to the virtual IP (SNAT), so the client only ever talks to `10.0.0.5`, the remaining packets of the connection are forwarded by the switches alone
    * __Monitoring:__ in the background the controller probes the health of both servers every 2 seconds and reads the port counters of all switches to calculate the throughput of every switch-to-switch link
    * __Failure Handling:__ when OpenFlow reports a link down, the controller marks the paths using it as down, clears all flow tables and every connection is routed again on its next packet, using the backup path, when the link comes back the same happens and traffic returns to the fast path, a server that stops answering probes is removed from server selection until it answers again
    * __Expected Behavior:__ requests from Singapore go to India and requests from Canada go to Europe over the fast path, if a mirror dies its clients move to the other mirror, if the fast link dies traffic moves to the slow link and returns when the fast link is repaired, if the nearest mirror is overloaded the extra requests overflow to the other mirror
### __Complete Application Functionality__
  * __Serving actual files:__ `server.py` serves every file placed in the `content` folder, the content type is found from the file extension, files are streamed in 1 MB chunks so large files do not have to fit in memory
  * __Requesting files:__ `client.py <file name>`, the server IP is optional and defaults to the virtual IP `10.0.0.5`, the file name defaults to `kpb77.txt`, for example `python3 client.py hello.txt` serves `hello.txt` (given its there in the contents directory), the client prints the status line, number of bytes, RTT (time until the complete response has arrived) and throughput in Mbps, and saves the file with the name `received_hello`
  * __Multiple clients and servers:__ 2 clients, 2 mirrors, many concurrent connections (one daemon thread per connection on the server side)
  * __Error handling:__ `404` for unknown files and path tricks, `400` for malformed requests, idle client timeout (15 seconds) on the server, connection refusal and timeout handling on the client
  * Check out `client.py` and `server.py` to see the implementation, abundant comments are included in the implementation to explain how the code works
### __Dynamic SDN Functionality__
  * The SDN is implemented in `smart_controller.py`, every feature is done by the controller real time dynamically by installing, replacing or deleting OpenFlow flow rules
  * __Server selection (proximity & health & load):__ `select_server()` takes the servers that are alive, sorts them by the latency to the requesting client (`LATENCY` table), and uses the closest one with fewer than `MAX_SERVER_LOAD` (5) active connections, if all are overloaded the least loaded one is used, the number of active connections is tracked by the controller per server
  * __Server health monitoring:__ every `MONITOR_INTERVAL` (2 s) the controller sends a TCP `SYN` probe from a fake host (`10.0.0.250`) to port 8080 of every server, a `SYN-ACK` means the content server is accepting connections (so a killed server process is detected, not only a dead link), the controller then sends a `RST` so no half open connections pile up in the server backlog, a server that did not answer for `PROBE_TIMEOUT` (6 s) is declared down, a server whose switch port goes down is also declared down, and it is added back as soon as it answers again
  * __Network monitoring:__ every 2 seconds the controller requests the port statistics of all switches and prints the throughput of every switch-to-switch link in Mbps (only for links that carry traffic), example: `monitor | s1 -> s2 | 9.41 Mbps`
  * __Primary / backup path routing:__ `DEFAULT_PATH = 'fast'`, all connections use the path via `s2`, the path via `s3` is only used when a link of the fast path is down
  * __Link failure detection and rerouting:__ OpenFlow `Port-Status` events tell the controller when a switch-to-switch link goes down or up, the controller recalculates which paths are usable, deletes all flows from all switches (and reinstalls the table-miss rule), and the next packet of every connection triggers a new `Packet-In`, so the connection is routed again over a working path, this also gives recovery when the link comes back (traffic returns to the fast path)
  * __Virtual IP (anycast) with NAT:__ per-connection flows (exact match on the TCP ports) rewrite the destination IP and MAC to the selected mirror at `s1`, and the source IP and MAC back to the virtual IP at `s4`, direct host-to-host traffic (ping, iperf) is not touched by NAT
  * __Proxy ARP:__ the controller answers all ARP requests (hosts, virtual IP, probe IP) itself
  * __Static baseline mode:__ starting the controller with `MODE=static ryu-manager smart_controller.py` gives the baseline used for the comparison: the virtual IP always goes to one fixed server (`h2`), always over the fast path, no health based selection, no load balancing, basic token handling, and no reaction to link or server failures
### __Challenging Scenarios / Robustness__
  * __Scenario 1 - mirror server failure:__ the server process of a mirror is killed, the controller detects it within about 6 seconds, new requests are served by the other mirror, when the mirror is restarted it is used again
  * __Scenario 2 - primary link failure:__ when the fast link `s1-s2` is taken down, all new connections use the slow path, when the link is repaired traffic returns to the fast path
  * __Scenario 3 - server overload:__ more concurrent requests than `MAX_SERVER_LOAD` for the nearest mirror, the extra requests overflow to the other mirror, if both are overloaded, it picks the least overloaded one
  * __Scenario 4 - server access link failure:__ the link between `s4` and a mirror is taken down, the port event removes the mirror from selection immediately
  * __Limitation:__ a TCP connection that is already open while its link or server dies cannot be saved (the client times out and retries), the new connections are the ones that recover
### __Challenging Testcases and Scenarios Demonstration__
  * __Pre requisite steps:__ follow the steps laid out in `README.md` present in the root directory of this repository, make sure `iperf` is installed (`sudo apt install -y iperf`), and clone this repository by typing
    ```
    git clone https://github.com/kpb77/cn-proj
    ```
  * __Step 0:__
    * This step must be done every time whenever a new bunch of unrelated tests has to be done, this is very important, run this command in a normal terminal window every time you have to perform a new bunch of tests
      ```
      sudo mn -c
      ```
  * __Preparing the content:__
    * Open a terminal window and change the working directory to `cn-proj/deliverable2`, then create some files to serve, the servers read the `content` folder of their working directory
      ```
      mkdir -p content
      fallocate -l 1M content/test1mb.bin
      fallocate -l 20M content/test20mb.bin
      cp content/test1mb.bin content/kpb77_test1mb.bin
      echo "yoyoyo this is kpb77" > content/hello.txt
      echo "anitya, dukkha, anatman" > content/kpb77.txt
      ```
  * __Setting things up:__
    * Open 6 terminal windows and change the working directory to `cn-proj/deliverable2`, and follow these steps in a strict sequential manner:
      * In the first terminal window (`term1`), type this
        ```
        source ~/ryu/bin/activate
        ```
        and this
        
        ```
        ryu-manager smart_controller.py
        ```
        this activates the Ryu virtual environment and starts the Ryu SDN Flow Controller in the proposed (`dynamic`) mode, for the baseline static routing experiments use `MODE=static ryu-manager smart_controller.py`
      * In the second terminal window (`term2`) type this
        ```
        sudo python3 topology.py
        ```
        this starts up the Mininet topology defined in `topology.py` and applies the latency between clients and mirrors (you will see lines like `*** h1 <-> h2: 40 ms`)

        now we start the 2 mirror servers h2 and h3 and start logging by these commands in the Mininet prompt
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
        this opens up the dynamic/live server logs for h2 (India)
      * In the fourth terminal window (`term4`) type this
        ```
        tail -f /tmp/h3.log
        ```
        this opens up the dynamic/live server logs for h3 (Europe)
      * In the fifth terminal window (`term5`) type this
        ```
        sudo tcpdump -i s3-eth1 -n tcp port 8080
        ```
        this is used to monitor the live TCP network traffic on the slow / backup path (via s3)
      * And in the sixth terminal window (`term6`) type this
        ```
        sudo tcpdump -i s2-eth1 -n tcp port 8080
        ```
        this is used to monitor the live TCP network traffic on the fast / primary path (via s2)
    * wait about 5 seconds after starting the servers, so that the controller has probed them and knows that they are alive
  * __Testcase 1:__ Check if both mirrors are listening and the latency is configured
    * For this, open up `term3` and `term4`, you should see `server listening on port 8080, serving files from 'content/'`, and run this in the Mininet prompt in `term2`
      ```
      h2 tc qdisc show dev h2-eth0
      ```
      this should list the `prio` queue and two `netem` entries (the delays for `h1` and `h4`)
  * __Testcase 2:__ Check if topology is running, controller can program switches and latency is emulated
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
      h1 ping -c 3 10.0.0.2
      ```

      ```
      h1 ping -c 3 10.0.0.3
      ```
    * the first ping (Singapore to India) should show around 45 ms and the second one (Singapore to Europe) around 165 ms, and the controller logs in `term1` show the switches being programmed
  * __Testcase 3:__ File delivery and fast path used by default
    * Run this in the Mininet prompt in `term2`
      ```
      h1 python3 client.py test20mb.bin
      ```
    * the client prints the status line, the RTT and the throughput and saves `received_test20mb.bin`, the TCP traffic is seen in `term6` (fast path) and nothing is seen in `term5` (slow path), the controller logs the selected mirror and the path
  * __Testcase 4:__ Proximity based server selection
    * Run these commands in the Mininet prompt in `term2`
      ```
      h1 python3 client.py test1mb.bin
      ```

      ```
      h4 python3 client.py test1mb.bin
      ```
    * the controller logs show `Singapore -> India, 40 ms` for `h1` and `Canada -> Europe, 90 ms` for `h4`, the file is served by `h2` (seen in `term3`) for `h1` and by `h3` (seen in `term4`) for `h4`, both clients used the same virtual IP
  * __Testcase 5:__ Load balancing (server overload)
    * Run this in the Mininet prompt in `term2`, 8 concurrent requests from the same client
      ```
      h1 for i in 1 2 3 4 5 6 7 8; do python3 client.py test1mb.bin & done; wait
      ```
    * the first 5 connections are served by the nearest mirror `h2` (the limit is `MAX_SERVER_LOAD` = 5) and the remaining 3 overflow to `h3`, this is seen in the controller log (`selected server`) and in `term3` and `term4`
  * __Testcase 6:__ Mirror server failure and recovery (failover)
    * Run these commands in the Mininet prompt in `term2`
      ```
      h2 pkill -f server.py
      ```
      
      ```
      h3 python3 -u server.py > /tmp/h3.log 2>&1 &
      ```
      wait about 6 seconds and run this
      ```
      h1 python3 client.py test1mb.bin
      ```
      the request from Singapore is now served by the Europe mirror (`h3`), now bring the mirror back
      ```
      h2 python3 -u server.py > /tmp/h2.log 2>&1 &
      ```
      after a few seconds the controller prints `server 10.0.0.2 is UP, back in server selection`, and the next request from `h1` is served by `h2` again
  * __Testcase 7:__ Primary link failure and recovery (path failover)
    * Run these commands in the Mininet prompt in `term2`
      ```
      link s1 s2 down
      ```

      ```
      h1 python3 client.py test20mb.bin
      ```
    * the controller prints `link s1-s2 is DOWN` and `flow tables cleared`, the traffic is seen in `term5` (slow / backup path) and the RTT is higher, now repair the link
      ```
      link s1 s2 up
      ```

      ```
      h1 python3 client.py test20mb.bin
      ```
    * the controller prints `link s1-s2 is UP`, and the traffic is back in `term6` (fast path)
  * __Testcase 8:__ Network monitoring and throughput
    * Run these commands in the Mininet prompt in `term2`
      ```
      h2 iperf -s &
      ```

      ```
      h1 iperf -c 10.0.0.2 -t 10
      ```
    * `term1` prints the throughput of the links carrying it every 2 seconds and `iperf` reports the end to end throughput
  * __Testcase 9:__ Server access link failure
    * Run these commands in the Mininet prompt in `term2`
      ```
      link s4 h2 down
      ```
      the controller prints `port of host 10.0.0.2 is DOWN` immediately and requests from `h1` are served by `h3`, bring it back with
      ```
      link s4 h2 up
      ```
  * __Testcase 10:__ Error handling (inherited from D1 and extended)
    * __Missing file (404):__
      ```
      h1 python3 client.py doesnotexist.bin
      ```
    * __Path traversal blocked (404):__
      ```
      h1 python3 client.py ../server.py
      ```
    * __Malformed request (400):__
      ```
      h1 python3 -c "import socket; s=socket.socket(); s.connect(('10.0.0.2',8080)); s.send(b'HELLO\r\n\r\n'); print(s.recv(4096).decode())"
      ```
    * __Idle client timeout:__
      ```
      h1 python3 -c "import socket,time; s=socket.socket(); s.connect(('10.0.0.2',8080)); time.sleep(8)" &
      ```

      ```
      h4 python3 client.py hello.txt
      ```
      the idle connection does not block the other client
    * __Connection refused (client side error handling):__ stop a mirror and request from it directly
      ```
      h3 pkill -f server.py
      ```

      ```
      h1 python3 client.py hello.txt 10.0.0.3
      ```
      this prints the standard `connection failed` message (direct IPs are not load balanced or failed over, only the virtual IP is)
  * __Baseline comparison:__ stop everything, run `sudo mn -c`, start the controller with `MODE=static ryu-manager smart_controller.py`, start the topology and the servers again, and repeat the test cases to observe the differences
