# Smart SDN Controller

import os
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, arp

# custom token that marks a request as priority content
TOKEN = "kpb77"

# port that the content server listens on
SERVER_PORT = 8080

# primary path used by all traffic, the other path (s3, slow) is the backup that is only used while the primary path is down
DEFAULT_PATH = 'fast'

# 'dynamic' is the proposed approach (load balancing, failover, rerouting), 'static' is the baseline (fixed server, fixed path, no recovery)
# selected when starting the controller, e.g. MODE=static ryu-manager simple_controller.py
MODE = os.environ.get('MODE', 'dynamic')

# virtual IP and MAC of the content service, clients send requests here and the controller picks the real server
VIP = '10.0.0.5'
VMAC = '00:00:00:00:00:05'

# the baseline always sends the virtual IP to this server
STATIC_SERVER = '10.0.0.2'

# real content servers that can be selected behind the virtual IP
SERVERS = ['10.0.0.2', '10.0.0.3']

# location of every host, h2 is the mirror in India, h3 is the mirror in Europe, h1 is the client in Singapore, h4 is the client in Canada
LOCATIONS = {
    '10.0.0.1': 'Singapore',
    '10.0.0.4': 'Canada',
    '10.0.0.2': 'India',
    '10.0.0.3': 'Europe',
}

# latency in ms from every client to every server, (client IP, server IP): latency, the lowest latency server is the primary choice
LATENCY = {
    ('10.0.0.1', '10.0.0.2'): 40,
    ('10.0.0.1', '10.0.0.3'): 160,
    ('10.0.0.4', '10.0.0.3'): 90,
    ('10.0.0.4', '10.0.0.2'): 220,
}

# a server with this many active connections counts as overloaded, the next closest server is used instead
MAX_SERVER_LOAD = 5

# fake source used by the controller to probe the health of the servers
PROBE_IP = '10.0.0.6'
PROBE_MAC = '00:00:00:00:00:06'
PROBE_PORT = 7070

# seconds between two monitoring rounds (port statistics and server probes)
MONITOR_INTERVAL = 2

# a server is declared down if it did not answer a probe for this many seconds
PROBE_TIMEOUT = 6

# seconds after which a connection stops counting as load on its server
CONN_LIFETIME = 20

# switch-to-switch ports, (from switch, to switch): port on the from switch
# port numbers follow the link order in topology.py
LINKS = {
    (1, 2): 3, (2, 1): 1,
    (1, 3): 4, (3, 1): 1,
    (2, 4): 2, (4, 2): 1,
    (3, 4): 2, (4, 3): 2,
}

# reverse view of the links, (switch, port): neighbour switch
LINK_PORTS = {(a, p): b for (a, b), p in LINKS.items()}

# host table, IP: (MAC, switch, port)
HOSTS = {
    '10.0.0.1': ('00:00:00:00:00:01', 1, 1),
    '10.0.0.4': ('00:00:00:00:00:04', 1, 2),
    '10.0.0.2': ('00:00:00:00:00:02', 4, 3),
    '10.0.0.3': ('00:00:00:00:00:03', 4, 4),
}

# IPs the controller answers ARP requests for, so ARP never depends on flooding (works even when a link is down)
ARP_TABLE = {ip: info[0] for ip, info in HOSTS.items()}
ARP_TABLE[VIP] = VMAC
ARP_TABLE[PROBE_IP] = PROBE_MAC

# switch sequence of each path, s2 is the fast path (2 ms) and s3 is the slow path (10 ms)
PATHS = {
    'fast': [1, 2, 4],
    'slow': [1, 3, 4],
}

# ports excluded from flooding to break the s1-s2-s4-s3 ring (s3 port 2 <-> s4 port 2 is the slow s3-s4 link)
# only used for non-IP traffic, IP traffic is routed along an explicit path
BLOCKED_FLOOD_PORTS = {
    3: {2},
    4: {2},
}


class D2ContentController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(D2ContentController, self).__init__(*args, **kwargs)

        # datapath object of every connected switch (DPID: datapath), needed to install flows along a whole path
        self.datapaths = {}

        # state of every content connection (client IP, client port): server, path, token flag, last activity
        self.conns = {}

        # switch-to-switch links that are currently down, stored as {switch a, switch b}
        self.down_links = set()

        # availability of each path, a path is down if any of its links is down
        self.path_up = {'fast': True, 'slow': True}

        # servers whose switch port is down
        self.host_down = set()

        # time of the last probe answer of every server, 0 means not proven alive yet
        self.last_ok = {ip: 0 for ip in SERVERS}

        # last reported availability of every server, used to print only the changes
        self.alive_state = {}

        # transmitted bytes of every switch-to-switch port at the previous monitoring round
        self.prev_bytes = {}

        # start the monitoring loop in the background
        self.monitor_thread = hub.spawn(self.monitor_loop)

        print(f"OpenFlow 1.3 initialized, mode: {MODE}")

    # installs the table-miss (no match in switch flow table) flow rule that redirects unmapped traffic to the controller
    def install_table_miss(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    # configures each switch with baseline table-miss flow rule
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):

        # gives details about the switch to Ryu
        datapath = ev.msg.datapath

        # remember the switch so flows can be installed on it later
        self.datapaths[datapath.id] = datapath

        # install table-miss flow rule in switch
        self.install_table_miss(datapath)
        print(f"switch {datapath.id} ready")

    # adds/installs custom forwarding rules to switch hardware
    def add_flow(self, datapath, priority, match, actions, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # package routing instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        # adding a rule with the same match and priority replaces the old one, which is how a flow is moved to another path
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst, idle_timeout=idle_timeout)

        # send the rule to the switch hardware
        datapath.send_msg(mod)

    # removes every flow rule from every switch, so all connections are routed again on their next packet (used on failure and recovery)
    def flush_flows(self):
        for datapath in self.datapaths.values():
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser

            mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE, out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY, match=parser.OFPMatch())
            datapath.send_msg(mod)

            # the delete also removed the table-miss rule, so it has to be installed again
            self.install_table_miss(datapath)
        print("flow tables cleared, connections will be routed again")

    # builds the list of (switch, output port) pairs a packet crosses from src_ip to dst_ip on the given path
    def get_hops(self, src_ip, dst_ip, name):
        src_sw = HOSTS[src_ip][1]
        dst_sw = HOSTS[dst_ip][1]

        # both hosts on the same switch, no path needed
        if src_sw == dst_sw:
            path = [src_sw]
        else:
            path = list(PATHS[name])
            if path[0] != src_sw:
                path.reverse()

        hops = []
        for i, sw in enumerate(path):

            # last switch hands the packet to the host, others forward to the next switch
            if i == len(path) - 1:
                out = HOSTS[dst_ip][2]
            else:
                out = LINKS[(sw, path[i + 1])]
            hops.append((sw, out))
        return hops

    # recalculates which paths are usable from the list of failed links
    def update_paths(self):
        for name, seq in PATHS.items():
            self.path_up[name] = all(frozenset((seq[i], seq[i + 1])) not in self.down_links for i in range(len(seq) - 1))

    # returns the preferred path if it is up, otherwise the other one, None if both are down
    def first_up(self, preferred):
        other = 'fast' if preferred == 'slow' else 'slow'
        for name in (preferred, other):
            if self.path_up[name]:
                return name
        return None

    # path of a content connection, token connections use the fast path, the baseline never changes path
    def select_path(self, c):
        if MODE == 'static':
            return DEFAULT_PATH
        return self.first_up('fast' if c['token'] else DEFAULT_PATH)

    # path of all other traffic (ping, iperf, ...)
    def plain_path(self):
        if MODE == 'static':
            return DEFAULT_PATH
        return self.first_up(DEFAULT_PATH)

    # a server is available if it answered a probe recently and its switch port is up
    def server_alive(self, ip):
        return ip not in self.host_down and (time.time() - self.last_ok[ip]) < PROBE_TIMEOUT

    # proximity based server selection, picks the available server with the lowest latency to the client
    # if that server is overloaded the next closest one is used, if all are overloaded the one with the fewest active connections is used
    # the baseline always uses one fixed server
    def select_server(self, client_ip):
        if MODE == 'static':
            return STATIC_SERVER

        # health, servers that are down are never selected
        alive = [ip for ip in SERVERS if self.server_alive(ip)]
        if not alive:
            return None

        # load, active connections of every available server
        now = time.time()
        load = {ip: 0 for ip in alive}
        for c in self.conns.values():
            if c['server'] in load and now - c['last'] < CONN_LIFETIME:
                load[c['server']] += 1

        # proximity, closest server first
        alive.sort(key=lambda ip: LATENCY.get((client_ip, ip), 1000))
        for ip in alive:
            if load[ip] < MAX_SERVER_LOAD:
                return ip
        return min(alive, key=lambda ip: load[ip])

    # describes one direction of a connection as a list of (switch, output port, source IP, destination IP, header rewrites) per switch
    # with the virtual IP, the first switch rewrites the destination to the real server, the server side switch rewrites the source of replies back to the virtual IP
    def direction(self, c, forward):
        if forward:
            src, dst = c['client'], c['server']
        else:
            src, dst = c['server'], c['client']

        hops = self.get_hops(src, dst, c['path'])
        result = []
        for i, (sw, out) in enumerate(hops):
            seen_src, seen_dst = src, dst
            sets = []
            if c['vip']:
                if forward and i == 0:
                    seen_dst = VIP
                    sets = [('eth_dst', HOSTS[c['server']][0]), ('ipv4_dst', c['server'])]
                if not forward:
                    if i == 0:
                        sets = [('eth_src', VMAC), ('ipv4_src', VIP)]
                    else:
                        seen_src = VIP
            result.append((sw, out, seen_src, seen_dst, sets))
        return result

    # turns header rewrites and an output port into OpenFlow actions
    def build_actions(self, parser, sets, out):
        actions = [parser.OFPActionSetField(**{field: value}) for field, value in sets]
        actions.append(parser.OFPActionOutput(out))
        return actions

    # actions the given switch applies to a packet of the connection in the given direction, None if the switch is not on the path
    def conn_actions(self, parser, c, forward, dpid):
        for sw, out, s, d, sets in self.direction(c, forward):
            if sw == dpid:
                return self.build_actions(parser, sets, out)
        return None

    # installs forward and reverse rules for a content connection along its chosen path
    def install_conn(self, c, monitor):
        for forward in (True, False):
            ports = (c['cport'], SERVER_PORT) if forward else (SERVER_PORT, c['cport'])
            for i, (sw, out, s, d, sets) in enumerate(self.direction(c, forward)):
                datapath = self.datapaths.get(sw)
                if datapath is None:
                    continue
                ofproto = datapath.ofproto
                parser = datapath.ofproto_parser

                actions = self.build_actions(parser, sets, out)

                # first switch also sends a copy of every request to the controller so the token can still be found in later packets
                if monitor and forward and i == 0:
                    actions.append(parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER))

                # exact TCP connection rules get higher priority than the generic per-protocol rules
                match = parser.OFPMatch(eth_type=0x0800, ipv4_src=s, ipv4_dst=d, ip_proto=6, tcp_src=ports[0], tcp_dst=ports[1])
                self.add_flow(datapath, 10, match, actions, idle_timeout=20)

    # installs generic per-protocol rules for both directions of other traffic (ping, iperf, ...)
    def install_plain(self, src_ip, dst_ip, proto, name):
        for s, d in ((src_ip, dst_ip), (dst_ip, src_ip)):
            for sw, out in self.get_hops(s, d, name):
                datapath = self.datapaths.get(sw)
                if datapath is None:
                    continue
                parser = datapath.ofproto_parser

                match = parser.OFPMatch(eth_type=0x0800, ipv4_src=s, ipv4_dst=d, ip_proto=proto)
                self.add_flow(datapath, 5, match, [parser.OFPActionOutput(out)], idle_timeout=60)

    # flood ports of a switch, every port except the incoming one and the blocked ones
    def flood_actions(self, datapath, in_port):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        blocked = BLOCKED_FLOOD_PORTS.get(datapath.id, set())
        ports = [p for p in datapath.ports if p < ofproto.OFPP_MAX and p != in_port and p not in blocked]
        return [parser.OFPActionOutput(p) for p in ports]

    # package and send current packet out of the target switch port
    def send_packet(self, datapath, msg, in_port, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    # sends a packet built by the controller itself out of one switch port
    def send_raw(self, datapath, port, pkt):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt.serialize()
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER, in_port=ofproto.OFPP_CONTROLLER, actions=[parser.OFPActionOutput(port)], data=pkt.data)
        datapath.send_msg(out)

    # answers an ARP request on behalf of the target (real hosts, virtual IP and probe IP)
    def send_arp_reply(self, datapath, in_port, arp_pkt):
        mac = ARP_TABLE[arp_pkt.dst_ip]

        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(ethertype=0x0806, dst=arp_pkt.src_mac, src=mac))
        pkt.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac=mac, src_ip=arp_pkt.dst_ip, dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip))
        self.send_raw(datapath, in_port, pkt)

    # sends a TCP probe (SYN or RST) from the controller to a content server
    def send_probe(self, server_ip, bits, seq, ack=0):
        datapath = self.datapaths.get(HOSTS[server_ip][1])
        if datapath is None:
            return

        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(ethertype=0x0800, dst=HOSTS[server_ip][0], src=PROBE_MAC))
        pkt.add_protocol(ipv4.ipv4(src=PROBE_IP, dst=server_ip, proto=6))
        pkt.add_protocol(tcp.tcp(src_port=PROBE_PORT, dst_port=SERVER_PORT, seq=seq, ack=ack, offset=5, bits=bits, window_size=1024))
        self.send_raw(datapath, HOSTS[server_ip][2], pkt)

    # a SYN-ACK from the server means the content server is accepting connections, the RST closes the half open connection again
    def handle_probe_reply(self, pkt, ip_pkt):
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        if ip_pkt.src in self.last_ok and tcp_pkt and (tcp_pkt.bits & tcp.TCP_SYN) and (tcp_pkt.bits & tcp.TCP_ACK):
            self.last_ok[ip_pkt.src] = time.time()
            self.send_probe(ip_pkt.src, tcp.TCP_RST, tcp_pkt.ack)

    # background loop, probes server availability and asks every switch for port statistics
    def monitor_loop(self):
        while True:
            hub.sleep(MONITOR_INTERVAL)

            # server availability, a dead server is removed from selection and a recovered one is added back
            for ip in SERVERS:
                self.send_probe(ip, tcp.TCP_SYN, 1000)
                alive = self.server_alive(ip)
                if alive != self.alive_state.get(ip, alive):
                    print(f"\nmonitor | server {ip} is {'UP, back in server selection' if alive else 'DOWN, removed from server selection'}\n")
                self.alive_state[ip] = alive

            # network conditions, port statistics of every switch
            for datapath in list(self.datapaths.values()):
                ofproto = datapath.ofproto
                parser = datapath.ofproto_parser
                datapath.send_msg(parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY))

    # computes the throughput of every switch-to-switch link from the port byte counters
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_handler(self, ev):
        dpid = ev.msg.datapath.id
        for stat in ev.msg.body:
            key = (dpid, stat.port_no)
            if key not in LINK_PORTS:
                continue

            previous = self.prev_bytes.get(key, stat.tx_bytes)
            self.prev_bytes[key] = stat.tx_bytes
            mbps = (stat.tx_bytes - previous) * 8 / MONITOR_INTERVAL / 1e6

            # only report links that carry traffic
            if mbps > 0.01:
                print(f"monitor | s{dpid} -> s{LINK_PORTS[key]} | {mbps:.2f} Mbps")

    # handles link and server failures, and their recovery
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto
        port = msg.desc

        down = bool(port.state & ofproto.OFPPS_LINK_DOWN) or bool(port.config & ofproto.OFPPC_PORT_DOWN) or msg.reason == ofproto.OFPPR_DELETE

        # switch-to-switch port, a link failed or recovered
        neighbor = LINK_PORTS.get((dpid, port.port_no))
        if neighbor is not None:
            link = frozenset((dpid, neighbor))

            # both ends of a link report the event, only the first one changes anything
            if down == (link in self.down_links):
                return

            if down:
                self.down_links.add(link)
            else:
                self.down_links.discard(link)
            self.update_paths()
            print(f"\nlink s{dpid}-s{neighbor} is {'DOWN' if down else 'UP'} | fast path up: {self.path_up['fast']} | slow path up: {self.path_up['slow']}\n")

            # the baseline does not react, dynamic mode moves every connection to a working path
            if MODE == 'dynamic':
                self.flush_flows()
            return

        # host port, a server link failed or recovered
        for ip, (mac, sw, p) in HOSTS.items():
            if sw == dpid and p == port.port_no:
                if down:
                    self.host_down.add(ip)
                else:
                    self.host_down.discard(ip)
                print(f"\nport of host {ip} is {'DOWN' if down else 'UP'}\n")

    # handles packet misses, answers ARP, picks the server and path of each connection and installs hardware flow rules along it
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # extract client-side port and decode the packet data stream
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # block discovery protocols and IPv6 multicast to prevent loops
        if eth.ethertype in [0x88cc, 0x86dd]:
            return

        dpid = datapath.id

        # ARP requests are answered by the controller, this also makes the virtual IP reachable
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip in ARP_TABLE:
            self.send_arp_reply(datapath, in_port, arp_pkt)
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        # answers of the servers to the controller's health probes
        if ip_pkt and ip_pkt.dst == PROBE_IP:
            self.handle_probe_reply(pkt, ip_pkt)
            return

        # other non-IP traffic or unknown hosts are flooded along the loop-free tree
        if not ip_pkt or ip_pkt.src not in HOSTS or (ip_pkt.dst not in HOSTS and ip_pkt.dst != VIP):
            self.send_packet(datapath, msg, in_port, self.flood_actions(datapath, in_port))
            return

        tcp_pkt = pkt.get_protocol(tcp.tcp)

        # traffic that does not belong to the content service (ping, iperf, ...) just follows the default path
        if not tcp_pkt or SERVER_PORT not in (tcp_pkt.src_port, tcp_pkt.dst_port):
            if ip_pkt.dst not in HOSTS:
                return

            name = self.plain_path()
            if name is None:
                print("no path available, packet dropped")
                return

            self.install_plain(ip_pkt.src, ip_pkt.dst, ip_pkt.proto, name)

            # output port of the current switch on the chosen path
            out_port = dict(self.get_hops(ip_pkt.src, ip_pkt.dst, name)).get(dpid)
            if out_port is None:
                return

            print(f"switch {dpid} | {ip_pkt.src} -> {ip_pkt.dst} | {name} path | port {in_port} -> port {out_port}")
            self.send_packet(datapath, msg, in_port, [parser.OFPActionOutput(out_port)])
            return

        # only client requests decide the server and path of a connection, the key is always the client side socket
        is_request = tcp_pkt.dst_port == SERVER_PORT
        if is_request:
            key = (ip_pkt.src, tcp_pkt.src_port)
        else:
            key = (ip_pkt.dst, tcp_pkt.dst_port)

        now = time.time()
        c = self.conns.get(key)
        is_syn = (tcp_pkt.bits & tcp.TCP_SYN) and not (tcp_pkt.bits & tcp.TCP_ACK)

        # new connection, load balancing happens here for requests sent to the virtual IP
        if is_request and (c is None or (is_syn and now - c['last'] > CONN_LIFETIME)):
            use_vip = ip_pkt.dst == VIP
            server = self.select_server(ip_pkt.src) if use_vip else ip_pkt.dst
            if server is None:
                print(f"no server available for {ip_pkt.src}:{tcp_pkt.src_port}, request dropped")
                return

            c = {'client': ip_pkt.src, 'cport': tcp_pkt.src_port, 'server': server, 'vip': use_vip, 'path': None, 'token': False, 'last': now}
            self.conns[key] = c
            print(f"\nnew connection {ip_pkt.src}:{tcp_pkt.src_port} ({LOCATIONS[ip_pkt.src]}) -> {ip_pkt.dst}:{SERVER_PORT} | selected server {server} ({LOCATIONS[server]}, {LATENCY.get((ip_pkt.src, server), '?')} ms)")

        # reply of a connection the controller does not know, nothing to route
        elif c is None:
            return

        c['last'] = now

        # application layer text payload is the last element Ryu parsed
        payload = b""
        if pkt.protocols and isinstance(pkt.protocols[-1], (bytes, bytearray)):
            payload = bytes(pkt.protocols[-1])
        decoded = payload.decode('utf-8', errors='ignore')

        # track custom token
        token_found = TOKEN in decoded
        if token_found:
            print(f"\ntoken {TOKEN} detected on switch {dpid}\n")
            print(f"socket traffic: client {ip_pkt.src}:{tcp_pkt.src_port} -> port {tcp_pkt.dst_port}")

        # application event changes network behavior: token requests move to the fast path (the baseline ignores the token)
        if token_found and is_request and MODE == 'dynamic':
            c['token'] = True

        name = self.select_path(c)
        if name is None:
            print(f"no path available for {c['client']}:{c['cport']}, packet dropped")
            return

        previous = c['path']
        c['path'] = name

        # requests still on the default path keep being copied to the controller
        monitor = MODE == 'dynamic' and not c['token']

        # packet is a monitoring copy, the switch already forwarded it, only reroute if the path changed
        if msg.reason == ofproto.OFPR_ACTION:
            if name != previous:
                print(f"rerouting {c['client']}:{c['cport']} -> {c['server']}:{SERVER_PORT} | {previous} path -> {name} path {PATHS[name]}")
                self.install_conn(c, monitor)
            return

        # install rules on every switch of the path for both directions
        self.install_conn(c, monitor)

        # actions of the current switch on the chosen path, including the virtual IP rewrite
        actions = self.conn_actions(parser, c, is_request, dpid)
        if actions is None:
            return

        print(f"switch {dpid} | {ip_pkt.src}:{tcp_pkt.src_port} -> {ip_pkt.dst}:{tcp_pkt.dst_port} | server {c['server']} | {name} path")

        # send current packet out so it is not lost while rules are being installed
        self.send_packet(datapath, msg, in_port, actions)
