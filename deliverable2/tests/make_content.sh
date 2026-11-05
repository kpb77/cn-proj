#!/usr/bin/env bash
# make_content.sh - create the files the tests download.
#
# The server serves ./content/ (relative to deliverable2/). The default file
# "kpb77.txt" is not in the repo, so the tests create their own:
#   content/test_small.txt  1 KB  (fast; used to check WHICH server answers)
#   content/test_large.txt  5 MB  (slow at 10 Mbps, ~4 s; keeps connections open
#                                  long enough for the overload test)
# Idempotent: a file that already exists with the right size is left alone.
# Do NOT commit these files (5 MB); `git add deliverable2/tests` only.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTENT="$HERE/../content"
mkdir -p "$CONTENT"

make_file() {
    local name="$1" size="$2" f="$CONTENT/$1"
    if [ -f "$f" ] && [ "$(stat -c %s "$f")" -eq "$size" ]; then
        echo "ok (already exists): content/$name ($size bytes)"
        return
    fi
    # `yes` repeats a text line forever, `head -c` cuts it to exactly $size bytes.
    # `yes` dies with SIGPIPE when head finishes, so ignore that exit status.
    (yes "SDN smart content delivery test data 0123456789 abcdefghijklmnopqrstuvwxyz" \
        | head -c "$size" > "$f") || true
    echo "created: content/$name ($(stat -c %s "$f") bytes)"
}

make_file test_small.txt 1024
make_file test_large.txt 5242880
