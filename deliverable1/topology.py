from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class SDNDeliveryTopo(Topo):
    def build(self):

        # Switches
        s1 = self.addSwitch('s1', dpid='0000000000000001') # Client Side Switch
        s2 = self.addSwitch('s2', dpid='0000000000000002') # Fast Path (2 ms)
        s3 = self.addSwitch('s3', dpid='0000000000000003') # Slow Path (10 ms)
        s4 = self.addSwitch('s4', dpid='0000000000000004') # Server Side Switch

        # Clients
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:04:04')

        # Server
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')

        # Links
        self.addLink(h1, s1)
        self.addLink(h4, s1)
        self.addLink(s1, s2, bw=10, delay='2ms')
        self.addLink(s1, s3, bw=10, delay='10ms')
        self.addLink(s2, s4, bw=10, delay='2ms')
        self.addLink(s3, s4, bw=10, delay='10ms')
        self.addLink(s4, h2)
        self.addLink(s4, h3)

def run():
    topo = SDNDeliveryTopo()
    net = Mininet(topo=topo, switch=OVSSwitch, controller=None, autoSetMacs=True, link=TCLink)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()