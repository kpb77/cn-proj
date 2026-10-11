# Simple SDN Controller

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp

# custom token that marks a request as priority content
TOKEN = "PES1UG25CS255"

# port that the content server listens on
SERVER_PORT = 8080

# path used by all traffic that does not carry the token
DEFAULT_PATH = 'slow'

# switch-to-switch ports, (from switch, to switch): port on the from switch
# port numbers follow the link order in topology.py
LINKS = {
    (1, 2): 3, (2, 1): 1,
    (1, 3): 4, (3, 1): 1,
    (2, 4): 2, (4, 2): 1,
    (3, 4): 2, (4, 3): 2,
}

# host table, IP: (MAC, switch, port)
HOSTS = {
    '10.0.0.1': ('00:00:00:00:00:01', 1, 1),
    '10.0.0.4': ('00:00:00:00:00:04', 1, 2),
    '10.0.0.2': ('00:00:00:00:00:02', 4, 3),
    '10.0.0.3': ('00:00:00:00:00:03', 4, 4),
}

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


class D1ContentController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(D1ContentController, self).__init__(*args, **kwargs)

        # datapath object of every connected switch (DPID: datapath), needed to install flows along a whole path
        self.datapaths = {}

        # path chosen for every TCP connection (connection key: path name)
        self.flow_path = {}

        print("OpenFlow 1.3 initialized")

    # configures each switch with baseline table-miss (no match in switch flow table) flow rule to redirect unmapped traffic to the controller
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):

        # gives details about the switch to Ryu
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # remember the switch so flows can be installed on it later
        self.datapaths[datapath.id] = datapath

        # install table-miss flow rule in switch
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
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

    # builds the match for one direction of a connection (exact TCP connection, or all traffic of one IP protocol)
    def make_match(self, parser, src_ip, dst_ip, proto, ports):
        if proto == 6 and ports:
            return parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip, ip_proto=6, tcp_src=ports[0], tcp_dst=ports[1])
        return parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip, ip_proto=proto)

    # installs flow rules for one direction on every switch of the path
    def install_hops(self, hops, src_ip, dst_ip, proto, ports, monitor):
        for i, (sw, out) in enumerate(hops):
            datapath = self.datapaths.get(sw)
            if datapath is None:
                continue
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser

            actions = [parser.OFPActionOutput(out)]

            # first switch also sends a copy of every request to the controller so the token can still be found in later packets
            if monitor and i == 0:
                actions.append(parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER))

            # exact TCP connection rules get higher priority than the generic per-protocol rules
            priority = 10 if ports else 5
            match = self.make_match(parser, src_ip, dst_ip, proto, ports)
            self.add_flow(datapath, priority, match, actions, idle_timeout=60)

    # installs forward and reverse rules for a connection along the chosen path
    def install_path(self, src_ip, dst_ip, proto, ports, name, monitor):
        fwd = self.get_hops(src_ip, dst_ip, name)
        rev = self.get_hops(dst_ip, src_ip, name)
        rev_ports = (ports[1], ports[0]) if ports else None

        self.install_hops(fwd, src_ip, dst_ip, proto, ports, monitor)
        self.install_hops(rev, dst_ip, src_ip, proto, rev_ports, False)

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

    # handles packet misses, picks the path of each connection and installs hardware flow rules along it
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

        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        # non-IP traffic (like ARP) or unknown hosts are flooded along the loop-free tree
        if not ip_pkt or ip_pkt.src not in HOSTS or ip_pkt.dst not in HOSTS:
            self.send_packet(datapath, msg, in_port, self.flood_actions(datapath, in_port))
            return

        ports = None
        monitor = False
        name = DEFAULT_PATH

        # parse TCP fields for socket monitoring
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        if tcp_pkt:
            ports = (tcp_pkt.src_port, tcp_pkt.dst_port)

            # same key for both directions of a connection
            conn = tuple(sorted([(ip_pkt.src, tcp_pkt.src_port), (ip_pkt.dst, tcp_pkt.dst_port)]))

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

            # only client requests decide the path of a connection
            is_request = tcp_pkt.dst_port == SERVER_PORT
            previous = self.flow_path.get(conn)

            # application event changes network behavior: token requests move to the fast path
            if token_found and is_request:
                self.flow_path[conn] = 'fast'
            name = self.flow_path.setdefault(conn, DEFAULT_PATH)

            # requests still on the default path keep being copied to the controller
            monitor = is_request and name != 'fast'

            # packet is a monitoring copy, the switch already forwarded it, only reroute if the path changed
            if msg.reason == ofproto.OFPR_ACTION:
                if name != previous:
                    print(f"rerouting {ip_pkt.src}:{tcp_pkt.src_port} -> {ip_pkt.dst}:{tcp_pkt.dst_port} | {previous} path -> {name} path {PATHS[name]}")
                    self.install_path(ip_pkt.src, ip_pkt.dst, ip_pkt.proto, ports, name, monitor)
                return

        # install rules on every switch of the path for both directions
        self.install_path(ip_pkt.src, ip_pkt.dst, ip_pkt.proto, ports, name, monitor)

        # output port of the current switch on the chosen path
        out_port = dict(self.get_hops(ip_pkt.src, ip_pkt.dst, name)).get(dpid)
        if out_port is None:
            return

        if tcp_pkt:
            print(f"switch {dpid} | {ip_pkt.src}:{tcp_pkt.src_port} -> {ip_pkt.dst}:{tcp_pkt.dst_port} | {name} path | port {in_port} -> port {out_port}")
        else:
            print(f"switch {dpid} | {ip_pkt.src} -> {ip_pkt.dst} | {name} path | port {in_port} -> port {out_port}")

        # send current packet out so it is not lost while rules are being installed
        self.send_packet(datapath, msg, in_port, [parser.OFPActionOutput(out_port)])
