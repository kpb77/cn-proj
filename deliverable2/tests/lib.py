"""
lib.py - shared helpers for the D2 test / failure-scenario scripts.

Every test follows the same pattern:
  1. build the SAME Mininet topology as topology.py (SDNDeliveryTopo) and
     connect it to the Ryu controller that is ALREADY running,
  2. start the two servers (h2, h3) as background processes, remembering
     their PIDs so we can kill exactly one of them,
  3. run clients on h1 (or h4) that download a file through the VIP,
  4. decide which server answered by counting "sent file" lines in each
     server's log (the client itself does not print the server),
  5. print [PASS]/[FAIL] lines and exit non-zero on failure.

Run with the SYSTEM python (where mininet is installed), NOT the Ryu venv:
    sudo python3 tests/test_server_failure.py

Environment variables:
    MODE       dynamic (default) | static   -> must match how Ryu was started.
               In static mode the "recovery" steps are EXPECTED to fail, and
               a failure is then reported as PASS (baseline shows no recovery).
    CTRL_IP    controller address   (default 127.0.0.1)
    CTRL_PORT  controller port      (default: auto-detect 6653, then 6633)
    CTRL_LOG   optional path of the Ryu log (ryu-manager ... 2>&1 | tee FILE);
               if set, tests also grep it for the expected controller messages.
"""

import filecmp
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from functools import partial

HERE = os.path.dirname(os.path.abspath(__file__))        # deliverable2/tests
D2 = os.path.dirname(HERE)                               # deliverable2
CONTENT = os.path.join(D2, "content")
sys.path.insert(0, D2)                                   # so "import topology" works

MODE = os.environ.get("MODE", "dynamic").strip().lower()
CTRL_IP = os.environ.get("CTRL_IP", "127.0.0.1")
CTRL_LOG = os.environ.get("CTRL_LOG", "")

VIP = "10.0.0.5"
PORT = 8080
SMALL = "test_small.txt"
LARGE = "test_large.txt"

LOGDIR = "/tmp/d2_test_logs"          # server stdout logs (one per host)
PIDFILE = "/tmp/d2_test_pids"         # PIDs of servers we started (for cleanup)

RESULTS = []                          # list of (status, label)
_procs = {}                           # host name -> Popen of its server


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------
def say(msg):
    print(msg, flush=True)


def step(msg):
    say("\n=== %s" % msg)


def check(label, ok, expect_fail_in_static=False):
    """Record one PASS/FAIL line.

    expect_fail_in_static: this step is a *recovery* step. In MODE=static the
    controller has no recovery logic, so the step is supposed to FAIL; we then
    print PASS (the baseline behaved as expected). If it unexpectedly works in
    static mode we print FAIL, because the baseline would not be a baseline.
    """
    if MODE == "static" and expect_fail_in_static:
        if not ok:
            status, label = "PASS", label + "  (baseline: no recovery, as expected in MODE=static)"
        else:
            status, label = "FAIL", label + "  (worked in MODE=static - baseline should NOT recover)"
    else:
        status = "PASS" if ok else "FAIL"
    RESULTS.append((status, label))
    say("[%s] %s" % (status, label))
    return status == "PASS"


def warn(label):
    """Soft observation that never fails the test (e.g. optional log grep)."""
    RESULTS.append(("WARN", label))
    say("[WARN] %s" % label)


def finish():
    """Print totals and exit 0 only if nothing failed."""
    fails = sum(1 for s, _ in RESULTS if s == "FAIL")
    passes = sum(1 for s, _ in RESULTS if s == "PASS")
    say("\nSummary (MODE=%s): %d passed, %d failed" % (MODE, passes, fails))
    sys.exit(1 if fails else 0)


# --------------------------------------------------------------------------
# Controller helpers
# --------------------------------------------------------------------------
def _port_open(ip, port):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((ip, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def controller_port():
    """Use CTRL_PORT if set, otherwise find which OpenFlow port Ryu listens on."""
    if os.environ.get("CTRL_PORT"):
        return int(os.environ["CTRL_PORT"])
    for p in (6653, 6633):
        if _port_open(CTRL_IP, p):
            return p
    say("ERROR: no controller listening on %s:6653 or 6633." % CTRL_IP)
    say("Start Ryu first:  source ~/ryu/bin/activate; ryu-manager smart_controller.py")
    sys.exit(2)


def ctrl_mark():
    """Remember the current end of the controller log (so we only read NEW lines)."""
    if CTRL_LOG and os.path.exists(CTRL_LOG):
        return os.path.getsize(CTRL_LOG)
    return None


def ctrl_grep(mark, regex):
    """Return matching controller-log lines written after `mark`, or None if no log."""
    if mark is None:
        return None
    with open(CTRL_LOG, "r", errors="replace") as f:
        f.seek(mark)
        return [ln.rstrip() for ln in f if re.search(regex, ln)]


def ctrl_expect(mark, regex, what):
    """Optional check: is the expected controller log line present? WARN only."""
    hits = ctrl_grep(mark, regex)
    if hits is None:
        say("[INFO] CTRL_LOG not set - skipped controller-log check for: %s" % what)
    elif hits:
        say("[INFO] controller log has '%s': %s" % (what, hits[-1]))
    else:
        warn("controller log has no line matching /%s/ (%s)" % (regex, what))


# --------------------------------------------------------------------------
# Network + server management
# --------------------------------------------------------------------------
def kill_leftovers():
    """Kill servers started by an earlier, aborted run of these scripts.

    We kill by PID (from PIDFILE), never `pkill -f server.py`: all Mininet hosts
    share one PID namespace, so pkill would kill BOTH servers (and anything else).
    """
    if os.path.exists(PIDFILE):
        with open(PIDFILE) as f:
            for line in f:
                try:
                    os.kill(int(line.strip()), signal.SIGKILL)
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
        os.remove(PIDFILE)


def start_network():
    """Build the topology from topology.py and connect it to the running Ryu."""
    if os.geteuid() != 0:
        say("ERROR: Mininet needs root. Run with sudo.")
        sys.exit(2)
    for f in (SMALL, LARGE):
        if not os.path.exists(os.path.join(CONTENT, f)):
            say("ERROR: content/%s missing. Run tests/make_content.sh first." % f)
            sys.exit(2)

    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSSwitch
    from mininet.link import TCLink
    from topology import SDNDeliveryTopo      # owned by the teammate; imported, never edited

    kill_leftovers()
    os.makedirs(LOGDIR, exist_ok=True)
    port = controller_port()

    net = Mininet(topo=SDNDeliveryTopo(),
                  controller=None,
                  switch=partial(OVSSwitch, protocols="OpenFlow13"),
                  link=TCLink,                # TCLink applies the delay / bandwidth settings
                  waitConnected=False)
    net.addController("c0", controller=RemoteController, ip=CTRL_IP, port=port)
    net.start()
    if not net.waitConnected(timeout=20):
        say("ERROR: switches did not connect to the controller.")
        stop_network(net)
        sys.exit(2)

    say("Topology attachments (host -> switch):")
    for h in net.hosts:
        say("   %s %s -> %s" % (h.name, h.IP(), ", ".join(
            l.intf2.node.name if l.intf1.node == h else l.intf1.node.name
            for l in net.links if h in (l.intf1.node, l.intf2.node))))
    # Give the controller time to discover links (LLDP) and probe both servers.
    say("Waiting 6 s for controller topology discovery...")
    time.sleep(6)
    return net


def stop_network(net):
    stop_servers()
    try:
        net.stop()
    except Exception as e:                    # never hide the real test result
        say("[INFO] net.stop() raised: %s" % e)


def _record_pid(pid):
    with open(PIDFILE, "a") as f:
        f.write("%d\n" % pid)


def start_server(net, name):
    """Run `python3 -u server.py` inside host `name`; stdout goes to a log file.

    -u = unbuffered, otherwise the "sent file" lines would sit in a buffer and
    our log counting would see nothing. cwd=deliverable2 so ./content/ resolves.
    The Popen object gives us the exact PID, so we can later kill ONE server.
    """
    host = net.get(name)
    logf = open(os.path.join(LOGDIR, name + ".log"), "a")
    p = host.popen(["python3", "-u", os.path.join(D2, "server.py")],
                   cwd=D2, stdout=logf, stderr=subprocess.STDOUT)
    _procs[name] = p
    _record_pid(p.pid)
    say("started server on %s (pid %d)" % (name, p.pid))
    time.sleep(1)                             # let it bind the port


def stop_server(name):
    """Kill the server on ONE host by PID (simulates that server crashing)."""
    p = _procs.pop(name, None)
    if p and p.poll() is None:
        p.kill()
        p.wait()
        say("killed server on %s (pid %d)" % (name, p.pid))


def stop_servers():
    for name in list(_procs):
        stop_server(name)
    if os.path.exists(PIDFILE):
        os.remove(PIDFILE)


def reset_logs(names=("h2", "h3")):
    os.makedirs(LOGDIR, exist_ok=True)
    for n in names:
        open(os.path.join(LOGDIR, n + ".log"), "w").close()


# --------------------------------------------------------------------------
# Which server answered?
# --------------------------------------------------------------------------
def served_counts(names=("h2", "h3")):
    """Number of 'sent file' lines in each server log so far."""
    out = {}
    for n in names:
        path = os.path.join(LOGDIR, n + ".log")
        cnt = 0
        if os.path.exists(path):
            with open(path, errors="replace") as f:
                cnt = sum(1 for ln in f if "sent file" in ln)
        out[n] = cnt
    return out


def delta(before, after):
    return {n: after[n] - before[n] for n in after}


def who_served(d):
    """Name of the single server that served in delta `d`, else None."""
    got = [n for n, c in d.items() if c > 0]
    return got[0] if len(got) == 1 else None


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class Download:
    """Result of one client.py run."""
    def __init__(self, ok, elapsed, output, rc):
        self.ok, self.elapsed, self.output, self.rc = ok, elapsed, output, rc


def start_client(net, client, fname):
    """Launch client.py on host `client` in its OWN temp dir.

    client.py saves received_<file> in the current folder, so concurrent
    clients would overwrite each other; separate dirs avoid that.
    Returns (Popen, workdir, start_time).
    """
    wd = tempfile.mkdtemp(prefix="d2_%s_" % client)
    p = net.get(client).popen(["python3", os.path.join(D2, "client.py"), fname],
                              cwd=wd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True)
    return p, wd, time.time()


def finish_client(p, wd, t0, fname, timeout):
    """Wait for the client; success = exit 0 AND file identical to the original."""
    try:
        out, _ = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        rc = -1
        out = (out or "") + "\n[test harness] client timed out after %ds" % timeout
    elapsed = time.time() - t0
    recv = os.path.join(wd, "received_" + fname)
    ok = (rc == 0 and os.path.exists(recv) and
          filecmp.cmp(recv, os.path.join(CONTENT, fname), shallow=False))
    shutil.rmtree(wd, ignore_errors=True)
    return Download(ok, elapsed, out or "", rc)


def download(net, client, fname, timeout=25):
    """One blocking download of `fname` from VIP via host `client`."""
    p, wd, t0 = start_client(net, client, fname)
    return finish_client(p, wd, t0, fname, timeout)
