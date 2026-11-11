#!/usr/bin/env bash
# Idempotent: start the Sprint-5 campaign queue (2 workers) if no live master exists.
# Usage: bash scripts/s5/supervise.sh [extra queue.py args]   (e.g. --workers 2 --tiers A,B)
cd "$(dirname "$0")/../.." || exit 1
mkdir -p outputs/s5/logs
PIDF=outputs/s5/queue.pid
if [ -f "$PIDF" ] && kill -0 "$(cat $PIDF)" 2>/dev/null \
   && tr '\0' ' ' < /proc/"$(cat $PIDF)"/cmdline 2>/dev/null | grep -q "s5/queue.py"; then
  echo "queue master alive (pid $(cat $PIDF))"
  exit 0
fi
nohup nice -n 5 python3 scripts/s5/queue.py --workers 2 "$@" >> outputs/s5/logs/queue.log 2>&1 &
sleep 2
echo "queue master started (pid $(cat $PIDF 2>/dev/null || echo '?'))"
