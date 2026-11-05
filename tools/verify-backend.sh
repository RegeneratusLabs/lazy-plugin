#!/bin/bash
# Is the running dashboard backend newer or older than the plugin code it serves?
#
# The plugin API router is imported once, at startup. Routes added to plugin_api.py after that
# boot are a 404 while every older route keeps working — one dead button, everything else fine.
# This checks the only thing that matters: does the process predate the file?
#
#   ~/projects/lazy-plugin/tools/verify-backend.sh
#
# Exit 0 = backend is current. Exit 1 = stale; bounce the backend from a shell outside Hermes
# (README → "Restart the backend"), then run this again.
set -u

PORT="${PORT:-9119}"
PLUGIN_API="$HOME/projects/lazy-plugin/dashboard/plugin_api.py"
LOG="$HOME/.hermes/logs/gui.log"

pid=$(ss -ltnp 2>/dev/null | grep ":${PORT} " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
if [ -z "${pid:-}" ]; then
  echo "FAIL: nothing is listening on ${PORT}"
  exit 1
fi

started=$(ps -o lstart= -p "$pid" | sed 's/^ *//')
started_epoch=$(date -d "$started" +%s 2>/dev/null || echo 0)
mtime_epoch=$(stat -c %Y "$PLUGIN_API")
mounts=$(grep -c 'Mounted plugin API routes: /api/plugins/lazy-plugin/' "$LOG" 2>/dev/null || echo 0)
unit=$(systemctl --user is-active hermes-gateway.service 2>/dev/null || echo unknown)
loops=$(systemctl --user list-units --all 2>/dev/null | grep -c "auto-restart.*Dashboard" || true)

echo "port ${PORT}        pid ${pid}"
echo "process started  ${started}"
echo "plugin_api.py    $(stat -c %y "$PLUGIN_API" | cut -d. -f1)"
echo "mount log lines  ${mounts}"
echo "gateway unit     ${unit}"
[ "${loops:-0}" -gt 0 ] && echo "warning          ${loops} dashboard unit(s) stuck in auto-restart (port conflict?)"
echo

if [ "$started_epoch" -ge "$mtime_epoch" ]; then
  echo "OK: the backend started after the plugin code was last changed."
  echo "    Every route that exists on disk is live in that process."
  exit 0
fi

age=$(( mtime_epoch - started_epoch ))
echo "STALE: the backend started ${age}s BEFORE plugin_api.py was last modified."
echo "       Routes added since then do not exist in the running process (they 404)."
echo "       Bounce the backend from a shell outside Hermes, then run this again."
exit 1
