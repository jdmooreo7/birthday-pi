#!/bin/sh
# Save what we'd need to understand a problem, before a reboot or an update loses it.
# Run on the Pi from ~/birthday-pi: scripts/diag.sh
# Writes ~/birthday-pi-diag/diag-<date>.txt.gz, readable only by you, and keeps the newest 20.
# It holds logs and numbers only: no photos, no face data, no .env, no container settings.
set -u
umask 077
dir="$HOME/birthday-pi-diag"
mkdir -p "$dir"
out="$dir/diag-$(date +%Y%m%d-%H%M%S).txt.gz"

section() { printf '\n===== %s\n' "$1"; }

# Leftover jobs: our own processes, left running on their own (parent is init) for over an hour,
# that aren't the desktop or the kiosk; and files that were deleted but are still being written.
desktop='systemd --user|lwrespawn|kanshi|kiosk\.sh|systemd-inhibit|polkit|menu-cached|crashpad|Xwayland'
leftovers=$(ps -u "$(id -u)" -o pid=,ppid=,etimes=,args= 2>/dev/null \
  | awk '$2 == 1 && $3 > 3600' | grep -v -E "$desktop" | cut -c1-200)
deleted=$(for p in $(pgrep -u "$(id -u)"); do
  ls -l "/proc/$p/fd" 2>/dev/null | grep ' (deleted)$' | grep -v -E '/\.config/chromium/|org\.chromium\.|memfd:|/dev/shm/' \
    | sed -E "s|.* -> |pid $p writes |"
done)
{
  section "when";        date; uptime
  section "version";     git -C "$(dirname "$0")/.." describe --tags --always --dirty 2>&1
  section "containers";  docker ps -a --format '{{.Names}}  {{.Status}}' 2>&1
  for c in $(docker ps -aq 2>/dev/null); do
    docker inspect -f '{{.Name}} restarts={{.RestartCount}} oom={{.State.OOMKilled}} started={{.State.StartedAt}}' "$c" 2>&1
  done
  section "memory";      free -m; docker stats --no-stream --format '{{.Name}}  {{.MemUsage}}  {{.CPUPerc}}' 2>&1
  section "disk";        df -h / 2>&1
  section "leftover jobs (should be empty)"; printf '%s\n' "${leftovers:-none}" "${deleted:-}"
  section "power and temperature"; vcgencmd get_throttled 2>&1; vcgencmd measure_temp 2>&1
  section "journal, previous boot (last 2000 lines)"; journalctl -b -1 --no-pager -n 2000 2>&1
  section "journal, this boot, warnings and worse";   journalctl -b -p warning --no-pager -n 2000 2>&1
  for c in birthday-pi-app-1 birthday-pi-faces-1; do
    section "log: $c (last 2000 lines)"; docker logs --timestamps --tail 2000 "$c" 2>&1
  done
} | gzip > "$out"

ls -1t "$dir"/diag-*.txt.gz | tail -n +21 | while read -r old; do rm -f "$old"; done
echo "Saved $out"
if [ -n "$leftovers$deleted" ]; then
  echo "Note: jobs left running on the Pi (not part of Birthday Pi):"
  printf '%s\n' "$leftovers" "$deleted" | grep -v '^$' | sed 's/^/  /'
fi
