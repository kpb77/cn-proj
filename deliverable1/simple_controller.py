# Simple SDN Controller

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp

class D1ContentController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(D1ContentController, self).__init__(*args, **kwargs)

        # dictionary to store MAC mapping configurations per switch (DPID: {MAC: Port})
        self.mac_to_port = {}

        print("OpenFlow 1.3 initialized")

    # configures each switch with baseline table-miss (no match in switch flow table) flow rule to redirect unmapped traffic to the controller
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        # gives details about the switch to Ryu
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow rule in switch
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        print(f"switch {datapath.id} ready")

    # adds/installs custom forwarding rules to swithc hardware
    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # package routing instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        
        # check if packet is in switch memory
        if buffer_id is not None:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)

        # send the rule to the switch hardware
        datapath.send_msg(mod)

    # handles packet misses, learns MAC addresses, and installs hardware flow rules
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

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        # dynamically initialize switch mapping tables
        self.mac_to_port.setdefault(dpid, {})

        # map source MAC to incoming switch port
        self.mac_to_port[dpid][src] = in_port

        # look up output port or flood if unknown
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # parse IP and TCP fields for socket monitoring
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            tcp_pkt = pkt.get_protocol(tcp.tcp)
            if tcp_pkt:

                # slice headers to extract application layer text payload
                payload = msg.data[eth.MIN_LEN + ip_pkt.header_length * 4 + tcp_pkt.offset * 4:]
                try:
                    decoded = payload.decode('utf-8', errors='ignore')

                    # track custom token
                    if "PES1UG25CS255" in decoded:
                        print(f"\ntoken PES1UG25CS255 detected on switch {dpid}\n")
                        print(f"socket traffic: client {ip_pkt.src}:{tcp_pkt.src_port} -> port {tcp_pkt.dst_port}")
                except Exception:
                    pass
                
                print(f"switch {dpid} | {ip_pkt.src}:{tcp_pkt.src_port} -> {ip_pkt.dst}:{tcp_pkt.dst_port} | port {in_port} -> port {out_port}")

        # automate switching for next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id is not None:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        # send current packet out of the target switch port
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)