#!/usr/bin/env bash
# run_all.sh - run every D2 test and print one summary table.
#
# Prerequisites (see README.md):
#   * `sudo mn -c` was run BEFORE starting Ryu (never after: it kills Ryu)
#   * Ryu is running in another terminal (MODE=dynamic or MODE=static)
#   * export the same MODE here, e.g.  MODE=static ./tests/run_all.sh
#   * no `sudo python3 topology.py` session is open (two Mininets would clash)
#
# Usage (from deliverable2/):   ./tests/run_all.sh
# Exit code: 0 if no check FAILED, 1 otherwise, 2 for setup problems.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.." || exit 2

# Mininet needs root; re-run ourselves under sudo, keeping MODE / CTRL_* variables.
if [ "$EUID" -ne 0 ]; then
    exec sudo -E bash "$0" "$@"
fi

export MODE="${MODE:-dynamic}"
# System python (has mininet). Not the Ryu venv.
PY="${PY:-/usr/bin/python3}"
OUT=/tmp/d2_test_out
mkdir -p "$OUT"

bash "$HERE/make_content.sh" || exit 2

TESTS=(test_server_failure test_link_failure test_overload)
overall=0
declare -A RC

for t in "${TESTS[@]}"; do
    echo
    echo "################ $t (MODE=$MODE) ################"
    "$PY" "$HERE/$t.py" 2>&1 | tee "$OUT/$t.out"
    RC[$t]=${PIPESTATUS[0]}
    [ "${RC[$t]}" -ne 0 ] && overall=1
    sleep 3    # let the controller settle between Mininet restarts
done

echo
echo "==================== SUMMARY (MODE=$MODE) ===================="
printf "%-22s %-6s %s\n" "TEST" "RESULT" "PASS/FAIL/WARN lines"
for t in "${TESTS[@]}"; do
    p=$(grep -c '^\[PASS\]' "$OUT/$t.out"); f=$(grep -c '^\[FAIL\]' "$OUT/$t.out")
    w=$(grep -c '^\[WARN\]' "$OUT/$t.out")
    res=PASS; [ "${RC[$t]}" -ne 0 ] && res=FAIL
    printf "%-22s %-6s %s/%s/%s\n" "$t" "$res" "$p" "$f" "$w"
done
echo "-------------------------------------------------------------"
grep -h '^\[FAIL\]' "$OUT"/*.out 2>/dev/null
[ "$overall" -eq 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED (details above)"
exit $overall
