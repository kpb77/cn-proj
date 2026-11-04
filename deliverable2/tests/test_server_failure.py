#!/usr/bin/env python3
"""
test_server_failure.py - proves the controller detects a dead server and
fails over to the other one, then returns to the preferred server when it recovers.

Steps (client h1 prefers h2):
  1. both servers up      -> download via VIP must be served by h2
  2. kill h2 (by PID)     -> wait > PROBE_TIMEOUT (6 s) -> download must be served by h3
  3. restart h2           -> wait for the probe to see it -> served by h2 again

In MODE=static (fixed server 10.0.0.2, no recovery) step 2 is expected to FAIL.

Run:  sudo python3 tests/test_server_failure.py      (Ryu already running)
"""
import time
import lib

PROBE_TIMEOUT = 6          # controller declares a server DOWN ~6 s after it stops answering
MONITOR_INTERVAL = 2       # controller probes every 2 s
WAIT_DOWN = PROBE_TIMEOUT + MONITOR_INTERVAL + 2    # 10 s: safely past detection
WAIT_UP = MONITOR_INTERVAL * 3 + 2                  # 8 s: a few probe rounds


def main():
    net = lib.start_network()
    try:
        lib.reset_logs()
        mark = lib.ctrl_mark()
        lib.start_server(net, "h2")
        lib.start_server(net, "h3")
        time.sleep(MONITOR_INTERVAL * 2)            # let the controller mark both UP

        # ---- Step 1: normal operation -----------------------------------
        lib.step("1. Both servers up: h1 should be served by h2 (India)")
        before = lib.served_counts()
        d = lib.download(net, "h1", lib.SMALL)
        who = lib.who_served(lib.delta(before, lib.served_counts()))
        lib.check("download succeeded (%.2fs)" % d.elapsed, d.ok)
        lib.check("served by h2 (got %s)" % who, who == "h2")

        # ---- Step 2: kill h2 --------------------------------------------
        lib.step("2. Kill h2, wait %d s, download again: expect h3 (failover)" % WAIT_DOWN)
        lib.stop_server("h2")
        time.sleep(WAIT_DOWN)
        before = lib.served_counts()
        d = lib.download(net, "h1", lib.SMALL)
        who = lib.who_served(lib.delta(before, lib.served_counts()))
        lib.check("download still succeeds after h2 died", d.ok,
                  expect_fail_in_static=True)
        lib.check("served by h3 (got %s)" % who, who == "h3",
                  expect_fail_in_static=True)
        lib.ctrl_expect(mark, r"server 10\.0\.0\.2 is DOWN", "h2 declared DOWN")
        lib.ctrl_expect(mark, r"selected server 10\.0\.0\.3", "h3 selected")

        # ---- Step 3: restart h2 -----------------------------------------
        lib.step("3. Restart h2, wait %d s, download again: expect h2 back" % WAIT_UP)
        lib.start_server(net, "h2")
        time.sleep(WAIT_UP)
        before = lib.served_counts()
        d = lib.download(net, "h1", lib.SMALL)
        who = lib.who_served(lib.delta(before, lib.served_counts()))
        lib.check("download succeeded", d.ok)
        lib.check("served by h2 again (got %s)" % who, who == "h2")
    finally:
        lib.stop_network(net)
    lib.finish()


if __name__ == "__main__":
    main()
