#!/usr/bin/env python3
"""
test_overload.py - proves load balancing: the controller sends at most
MAX_SERVER_LOAD (5) connections from one region to the preferred server
(connections are counted over the last 20 s); the 6th and later connections
go to the next-closest server.

We start 8 clients on h1 almost together, each downloading the 5 MB file
(~4 s alone at 10 Mbps, so they overlap). Then we count "sent file" lines in
each server's log:
  expected (dynamic): h2 > 0 AND h3 > 0   (traffic was spread)
  expected (static):  h3 == 0             (everything goes to fixed h2)

Run:  sudo python3 tests/test_overload.py           (Ryu already running)
"""
import time
import lib

PARALLEL = 8              # > MAX_SERVER_LOAD (5)
STAGGER = 0.3             # seconds between launches so each opens its own flow
TIMEOUT = 150             # 8 x 5 MB share a 10 Mbps path: well under this


def main():
    net = lib.start_network()
    try:
        lib.reset_logs()
        mark = lib.ctrl_mark()
        lib.start_server(net, "h2")
        lib.start_server(net, "h3")
        time.sleep(4)

        lib.step("Launching %d parallel downloads of the 5 MB file from h1" % PARALLEL)
        before = lib.served_counts()
        running = []
        for _ in range(PARALLEL):
            running.append((lib.start_client(net, "h1", lib.LARGE)))
            time.sleep(STAGGER)

        # Wait for all clients; each has its own temp dir so nobody overwrites anybody.
        results = [lib.finish_client(p, wd, t0, lib.LARGE, TIMEOUT) for p, wd, t0 in running]
        done = sum(1 for r in results if r.ok)
        d = lib.delta(before, lib.served_counts())
        lib.say("Connections served per server: h2=%d  h3=%d" % (d["h2"], d["h3"]))

        lib.step("Checks")
        lib.check("all %d downloads completed (%d did)" % (PARALLEL, done), done == PARALLEL)
        lib.check("h2 (preferred) served some (%d)" % d["h2"], d["h2"] > 0)
        lib.check("overflow reached h3 (%d connections) - load was spread" % d["h3"],
                  d["h3"] > 0, expect_fail_in_static=True)
        lib.ctrl_expect(mark, r"selected server 10\.0\.0\.3", "h3 selected for overflow")
    finally:
        lib.stop_network(net)
    lib.finish()


if __name__ == "__main__":
    main()
