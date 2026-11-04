from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

# latency in ms between every client and every server, (client, server): latency
LATENCY = {
    ('h1', 'h2'): 40,   # Singapore -> India
    ('h1', 'h3'): 160,  # Singapore -> Europe
    ('h4', 'h3'): 90,   # Canada -> Europe
    ('h4', 'h2'): 220,  # Canada -> India
}

# IP of every client, used to tell the clients apart on the server side
CLIENT_IPS = {'h1': '10.0.0.1', 'h4': '10.0.0.4'}

class SDNDeliveryTopo(Topo):
    def build(self):

        # Switches
        s1 = self.addSwitch('s1', dpid='0000000000000001') # Client Side Switch
        s2 = self.addSwitch('s2', dpid='0000000000000002') # Fast Path (2 ms)
        s3 = self.addSwitch('s3', dpid='0000000000000003') # Slow Path (10 ms)
        s4 = self.addSwitch('s4', dpid='0000000000000004') # Server Side Switch

        # Clients
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01') # Singapore
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04') # Canada

        # Server
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02') # India Mirror
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03') # Europe Mirror

        # Links
        self.addLink(h1, s1)
        self.addLink(h4, s1)
        self.addLink(s1, s2, bw=10, delay='2ms')
        self.addLink(s1, s3, bw=10, delay='10ms')
        self.addLink(s2, s4, bw=10, delay='2ms')
        self.addLink(s3, s4, bw=10, delay='10ms')
        self.addLink(s4, h2)
        self.addLink(s4, h3)

# adds the geographic latency between clients and servers
# every server delays its replies depending on which client they go to, so each client-server pair gets its own latency
def add_location_latency(net):
    for server in ('h2', 'h3'):
        host = net.get(server)
        intf = f'{server}-eth0'

        # priority qdisc with 3 bands, all traffic goes to band 3 (no delay) unless a filter below moves it
        host.cmd(f'tc qdisc add dev {intf} root handle 1: prio bands 3 priomap 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2')

        # one band per client, with the latency of that client-server pair
        for band, client in enumerate(('h1', 'h4'), start=1):
            delay = LATENCY[(client, server)]
            host.cmd(f'tc qdisc add dev {intf} parent 1:{band} handle {band}0: netem delay {delay}ms')
            host.cmd(f'tc filter add dev {intf} parent 1: protocol ip prio 1 u32 match ip dst {CLIENT_IPS[client]}/32 flowid 1:{band}')
            info(f'*** {client} <-> {server}: {delay} ms\n')

def run():
    topo = SDNDeliveryTopo()
    net = Mininet(topo=topo, switch=OVSSwitch, controller=None, link=TCLink)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.start()
    add_location_latency(net)
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()