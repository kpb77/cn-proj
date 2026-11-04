#!/usr/bin/env python3
"""
test_link_failure.py - proves the controller reroutes over the slow path
(s1-s3-s4) when a link of the fast path (s1-s2-s4) goes down, and returns
to the fast path when the link comes back.

Steps (client h1):
  1. link up    -> download works over the fast path (2 ms/link)  [latency baseline]
  2. link down  -> `net.configLinkStatus('s2','s4','down')` -> download must STILL
                   work, via the slow path (10 ms/link) so latency is higher
  3. link up    -> download works again, latency back to the fast-path level

Latency is measured as the best of 3 downloads of the 1 KB file (small file =
time is dominated by round trips, not bandwidth). It is a WARN, not a FAIL,
if the difference is not visible, because process start-up adds noise.

In MODE=static (fixed fast path, no failure recovery) step 2 is expected to FAIL.

Configurable: FAIL_LINK="s2 s4" (default), CLIENT=h1 (default).
Run:  sudo python3 tests/test_link_failure.py       (Ryu already running)
"""
import os
import time
import lib

A, B = (os.environ.get("FAIL_LINK", "s2 s4").split() + ["s4"])[:2]
CLIENT = os.environ.get("CLIENT", "h1")
SETTLE = 6                   # seconds for the controller to see the port event and reroute


def best_time(net, n=3):
    """(all_ok, fastest elapsed) over n small downloads."""
    times, ok = [], True
    for _ in range(n):
        d = lib.download(net, CLIENT, lib.SMALL, timeout=15)
        ok = ok and d.ok
        if d.ok:
            times.append(d.elapsed)
    return ok, (min(times) if times else None)


def main():
    net = lib.start_network()
    try:
        lib.reset_logs()
        mark = lib.ctrl_mark()
        lib.start_server(net, "h2")
        lib.start_server(net, "h3")
        time.sleep(4)

        # ---- Step 1: fast path ------------------------------------------
        lib.step("1. Link %s-%s UP: download over the fast path" % (A, B))
        ok, fast = best_time(net)
        lib.check("download succeeded, best time %.3fs" % (fast or -1), ok)

        # ---- Step 2: link down ------------------------------------------
        lib.step("2. Link %s-%s DOWN: download must still work via slow path" % (A, B))
        net.configLinkStatus(A, B, "down")        # Mininet: bring both link ends down
        time.sleep(SETTLE)
        ok, slow = best_time(net)
        lib.check("download succeeded with link down, best time %.3fs" % (slow or -1),
                  ok, expect_fail_in_static=True)
        if MODE_IS_DYNAMIC() and fast and slow:
            if slow > fast:
                lib.say("[INFO] latency rose from %.3fs to %.3fs (slow path in use)" % (fast, slow))
            else:
                lib.warn("latency did not rise (%.3fs -> %.3fs); the client may not use "
                         "the failed link, or noise hides it. Check the controller log "
                         "for 'rerouting ... slow path'." % (fast, slow))
        lib.ctrl_expect(mark, r"link s\d-s\d is DOWN", "link DOWN event")
        lib.ctrl_expect(mark, r"rerouting.*slow path", "reroute onto slow path")

        # ---- Step 3: link up --------------------------------------------
        lib.step("3. Link %s-%s UP again: back on the fast path" % (A, B))
        net.configLinkStatus(A, B, "up")
        time.sleep(SETTLE)
        ok, back = best_time(net)
        lib.check("download succeeded, best time %.3fs" % (back or -1), ok)
        lib.ctrl_expect(mark, r"link s\d-s\d is UP", "link UP event")
    finally:
        lib.stop_network(net)
    lib.finish()


def MODE_IS_DYNAMIC():
    return lib.MODE != "static"


if __name__ == "__main__":
    main()
