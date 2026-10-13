#!/bin/sh
# Show the kiosk with test timings for a while, then restore the normal screen.
# Usage: test-screen.sh [QUERY] [SECONDS]
#   default: idle=5&photo=300&night=0-24 for 60 seconds (dim + photos after 5s idle)
QUERY="${1:-idle=5&photo=300&night=0-24}"
SECONDS_TO_RUN="${2:-60}"
DIR="$(cd "$(dirname "$0")" && pwd)"

# Borrow the desktop session's Wayland environment so Chromium draws on the monitor.
LABWC_PID="$(pgrep -u "$(id -u)" -x labwc | head -1)"
[ -n "$LABWC_PID" ] || { echo "desktop session (labwc) not running" >&2; exit 1; }
eval "$(tr '\0' '\n' < /proc/"$LABWC_PID"/environ | grep -E '^(WAYLAND_DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS)=' | sed 's/^/export /')"

restart_kiosk() {
  pkill -f /usr/lib/chromium/chromium; sleep 2
  BIRTHDAY_PI_URL="$1" setsid nohup "$DIR/kiosk.sh" >/dev/null 2>&1 &
}

echo "test: http://localhost:8080/?$QUERY for ${SECONDS_TO_RUN}s"
restart_kiosk "http://localhost:8080/?$QUERY"
sleep "$SECONDS_TO_RUN"
echo "restoring normal screen"
restart_kiosk "http://localhost:8080/"
