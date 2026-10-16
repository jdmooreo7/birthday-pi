#!/bin/sh
# The weekly pilot check: numbers only, safe to write down and take away. No names, dates or photos.
# Run on the Pi from ~/birthday-pi: scripts/pilot-stats.sh [days]   (default 7)
set -u
days=${1:-7}

echo "Birthday Pi $(git -C "$(dirname "$0")/.." describe --tags --always 2>/dev/null), $(date '+%Y-%m-%d %H:%M')"
echo "Up since: $(uptime -s)"
echo "Starts of the Pi on record: $(journalctl --list-boots --no-pager 2>/dev/null | tail -n +2 | wc -l)"
for c in birthday-pi-app-1 birthday-pi-faces-1; do
  docker inspect -f '{{.Name}}: {{.State.Health.Status}}, restarts {{.RestartCount}}, out of memory {{.State.OOMKilled}}' "$c" 2>&1 | sed 's#^/##'
done
docker stats --no-stream --format '{{.Name}}: {{.MemUsage}}' birthday-pi-app-1 birthday-pi-faces-1 2>&1
echo "Memory free: $(free -m | awk '/^Mem:/ {print $7}') MB; disk free: $(df -h / | awk 'NR==2 {print $4}')"
echo "Power and temperature: $(vcgencmd get_throttled 2>&1), $(vcgencmd measure_temp 2>&1)"
echo
docker exec birthday-pi-app-1 python -m birthday_pi.cli pilot-stats --days "$days"
