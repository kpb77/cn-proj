# D2 tests and failure scenarios

Automated checks for the SDN Smart Content Delivery System. They only *add*
files under `deliverable2/tests/`; the controller, topology, client and server
are not touched.

| File | Purpose |
|------|---------|
| `make_content.sh` | Creates `content/test_small.txt` (1 KB) and `content/test_large.txt` (5 MB) |
| `lib.py` | Shared helpers (build the topology, start/kill servers by PID, run clients, count which server answered, PASS/FAIL printing) |
| `test_server_failure.py` | Server crash and recovery |
| `test_link_failure.py` | Link failure, slow-path reroute, link recovery |
| `test_overload.py` | Load balancing above `MAX_SERVER_LOAD` |
| `run_all.sh` | Runs everything and prints a summary table |

## How the tests work

* Each test imports `SDNDeliveryTopo` from `topology.py`, builds the same
  Mininet network, and connects it to the Ryu controller you already started.
* Servers run as background processes started with their PID saved, so one
  server can be killed without touching the other (`pkill -f server.py` would
  kill both: all Mininet hosts share one PID namespace).
* The client does not print which server answered, so the tests count
  `sent file` lines in each server log (`/tmp/d2_test_logs/h2.log`, `h3.log`).
* Optional: if you start Ryu with `2>&1 | tee /tmp/ryu.log` and export
  `CTRL_LOG=/tmp/ryu.log`, tests also look for controller messages
  (`server 10.0.0.2 is DOWN`, `link s2-s4 is DOWN`, `selected server`,
  `rerouting ... slow path`). Missing lines only give a `[WARN]`.
* Each download goes in its own temp folder (the client saves
  `received_<file>` in the current folder) and is compared byte-for-byte
  with the original.

## Prerequisites

1. `cd deliverable2`
2. Clean Mininet **before** starting Ryu (never after, it kills Ryu):
   `sudo mn -c`
3. Terminal A (Ryu venv):
   ```
   source ~/ryu/bin/activate
   ryu-manager smart_controller.py 2>&1 | tee /tmp/ryu.log        # dynamic (default)
   # or the baseline:
   MODE=static ryu-manager smart_controller.py 2>&1 | tee /tmp/ryu.log
   ```
4. Terminal B (system Python, **not** the venv; run `deactivate` if needed).
   Close any open `sudo python3 topology.py` session first.
   ```
   ./tests/make_content.sh
   export CTRL_LOG=/tmp/ryu.log     # optional
   export MODE=dynamic              # must match how Ryu was started (or static)
   ```

## Running each test

```
sudo -E python3 tests/test_server_failure.py
sudo -E python3 tests/test_link_failure.py
sudo -E python3 tests/test_overload.py
# everything + summary:
./tests/run_all.sh
```

### test_server_failure.py (about 40 s)
1. Both servers up, h1 downloads via VIP -> served by **h2**.
2. h2 is killed by PID, wait 10 s (> `PROBE_TIMEOUT` 6 s), download -> served by **h3**.
3. h2 restarted, wait 8 s, download -> served by **h2** again.

Expected (dynamic):
```
[PASS] download succeeded (0.xxs)
[PASS] served by h2 (got h2)
[PASS] download still succeeds after h2 died
[PASS] served by h3 (got h3)
[PASS] download succeeded
[PASS] served by h2 again (got h2)
Summary (MODE=dynamic): 6 passed, 0 failed
```

### test_link_failure.py (about 60 s)
1. Fast path up: best of 3 small downloads (latency baseline).
2. `net.configLinkStatus('s2','s4','down')`, wait 6 s, download must still work over the slow
   path (10 ms/link) and be slower.
3. Link up, wait 6 s, download works again.

Expected (dynamic): all `[PASS]`, plus `[INFO] latency rose from 0.0xxs to 0.1xxs`.
Another link or client can be tried with `FAIL_LINK="s1 s2" CLIENT=h4`.

### test_overload.py (about 60 s)
8 parallel downloads of the 5 MB file from h1, started 0.3 s apart. The
first 5 go to h2, the rest overflow to h3.

Expected (dynamic): `Connections served per server: h2=5 h3=3` (exact split may vary
a little; the check is `h2 > 0` and `h3 > 0`).

## Showing the baseline fail (MODE=static)

Static mode has a fixed server (10.0.0.2), a fixed fast path and no failure recovery.
Restart Ryu in static mode, then run the tests with `MODE=static` so the scripts
know a failure of the recovery steps is the *expected* result:

```
# Terminal A: Ctrl+C Ryu, then
MODE=static ryu-manager smart_controller.py 2>&1 | tee /tmp/ryu.log
# Terminal B:
MODE=static ./tests/run_all.sh
```

Expected in static mode (shown as PASS because the baseline failed as expected):
* server failure, step 2: no download after h2 dies (client times out), nothing served by h3
* link failure, step 2: download fails once the fast-path link is down
* overload: everything is served by h2, `h3=0`

If one of these *works* in static mode the script prints `[FAIL] ... worked in MODE=static`.
Switch back to `MODE=dynamic` (restart Ryu) to see the real system recover.

## Notes and troubleshooting

* `sudo mn -c` is your job, **before** Ryu. Do not run it between tests.
* Scripts are idempotent: servers are killed by PID in a `finally` block, and
  leftovers from an aborted run are killed by PID at the next start.
* If a test is aborted hard and Mininet interfaces remain, stop Ryu, run
  `sudo mn -c`, then restart Ryu.
* Do not commit `content/test_*.txt` (5 MB). Only `git add deliverable2/tests`.
* `CTRL_PORT` can be set if Ryu does not listen on 6653/6633.
* If a test cannot find the topology class, check that `topology.py` exposes
  `SDNDeliveryTopo` and does not start the CLI at import time (it should be under
  `if __name__ == '__main__':`).
