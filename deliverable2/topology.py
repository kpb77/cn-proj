from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

# Geographic latency in ms between every client and server
LATENCY = {
    ('h1', 'h2'): 40,    # Singapore -> India
    ('h1', 'h3'): 160,   # Singapore -> Europe
    ('h1', 'h6'): 180,   # Singapore -> US

    ('h4', 'h2'): 220,   # Canada -> India
    ('h4', 'h3'): 90,    # Canada -> Europe
    ('h4', 'h6'): 50,    # Canada -> US

    ('h5', 'h2'): 100,   # Australia -> India
    ('h5', 'h3'): 250,   # Australia -> Europe
    ('h5', 'h6'): 170,   # Australia -> US
}

# Client IP addresses
CLIENT_IPS = {
    'h1': '10.0.0.1',
    'h4': '10.0.0.4',
    'h5': '10.0.0.5'
}


class SDNDeliveryTopo(Topo):

    def build(self):

        # Switches
        s1 = self.addSwitch('s1', dpid='0000000000000001')  # Client Side Switch
        s2 = self.addSwitch('s2', dpid='0000000000000002')  # Fast Path (2 ms)
        s3 = self.addSwitch('s3', dpid='0000000000000003')  # Slow Path (10 ms)
        s4 = self.addSwitch('s4', dpid='0000000000000004')  # Server Side Switch

        # Clients
        h1 = self.addHost('h1', ip='10.0.0.1/24',
                          mac='00:00:00:00:00:01')

        h4 = self.addHost('h4', ip='10.0.0.4/24',
                          mac='00:00:00:00:00:04')

        h5 = self.addHost('h5', ip='10.0.0.5/24',
                          mac='00:00:00:00:00:05')

        # Servers
        h2 = self.addHost('h2', ip='10.0.0.2/24',
                          mac='00:00:00:00:00:02')

        h3 = self.addHost('h3', ip='10.0.0.3/24',
                          mac='00:00:00:00:00:03')

        h6 = self.addHost('h6', ip='10.0.0.6/24',
                          mac='00:00:00:00:00:06')

        # Traffic Generator
        gen = self.addHost('gen', ip='10.0.0.7/24',
                           mac='00:00:00:00:00:07')

        # Traffic Sink
        sink = self.addHost('sink', ip='10.0.0.8/24',
                            mac='00:00:00:00:00:08')

        # Client and generator connections
        self.addLink(h1, s1)
        self.addLink(h4, s1)
        self.addLink(h5, s1)
        self.addLink(gen, s1)

        # Fast Path (2 ms)
        self.addLink(s1, s2, bw=10, delay='2ms')
        self.addLink(s2, s4, bw=10, delay='2ms')

        # Slow Path (10 ms)
        self.addLink(s1, s3, bw=10, delay='10ms')
        self.addLink(s3, s4, bw=10, delay='10ms')

        # Server and sink connections
        self.addLink(s4, h2)
        self.addLink(s4, h3)
        self.addLink(s4, h6)
        self.addLink(s4, sink)


# Add geographic latency between clients and servers
def add_location_latency(net):

    for server in ('h2', 'h3', 'h6'):

        host = net.get(server)
        intf = f'{server}-eth0'

        # Priority queue with 3 bands
        # Default traffic goes to band 3 (no additional delay)
        host.cmd(
            f'tc qdisc add dev {intf} root handle 1: '
            'prio bands 3 priomap 2 2 2 2 2 2 2 2 '
            '2 2 2 2 2 2 2 2'
        )

        # Assign one band to each client
        for band, client in enumerate(('h1', 'h4', 'h5'), start=1):

            delay = LATENCY[(client, server)]

            # Apply geographic delay
            host.cmd(
                f'tc qdisc add dev {intf} parent 1:{band} '
                f'handle {band}0: netem delay {delay}ms'
            )

            # Match outgoing packets based on destination IP
            host.cmd(
                f'tc filter add dev {intf} parent 1: '
                f'protocol ip prio 1 u32 '
                f'match ip dst {CLIENT_IPS[client]}/32 '
                f'flowid 1:{band}'
            )

            info(f'*** {client} <-> {server}: {delay} ms\n')


def run():

    topo = SDNDeliveryTopo()

    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        controller=None,
        link=TCLink
    )

    # Connect to remote SDN controller
    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6653
    )

    net.start()

    # Apply geographic latency
    add_location_latency(net)

    info('\n*** SDN Delivery Topology Started\n')
    info('*** 3 Clients: h1, h4, h5\n')
    info('*** 3 Servers: h2, h3, h6\n')
    info('*** Generator: gen\n')
    info('*** Sink: sink\n')

    CLI(net)

    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
