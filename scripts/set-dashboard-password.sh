#!/bin/sh
# Set (or change) the password for the dashboards, and start them.
# Run on the Pi from ~/birthday-pi:  scripts/set-dashboard-password.sh
# Asks for the password twice, stores only its hash in .env (readable by you alone),
# then starts Birthday Pi with the dashboards. Sign in as "admin".
set -u
cd "$(dirname "$0")/.." || exit 1

ask() {
  printf '%s' "$1" >&2
  stty -echo 2>/dev/null; IFS= read -r answer; stty echo 2>/dev/null
  printf '\n' >&2
  printf '%s' "$answer"
}
pw=$(ask "New dashboards password (not your Pi password): ")
[ ${#pw} -ge 8 ] || { echo "Use at least 8 characters. Nothing changed."; exit 1; }
again=$(ask "Type it again: ")
[ "$pw" = "$again" ] || { echo "The two didn't match. Nothing changed."; exit 1; }

# Hash it inside Caddy's own image. The password goes in on stdin, never on a command line.
echo "Making the hash (a few seconds)..."
hash=$(printf '%s\n' "$pw" | docker run --rm -i caddy:2.11.7-alpine caddy hash-password 2>/dev/null)
unset pw again
case "$hash" in
  '$2'*) ;;
  *) echo "Couldn't make the hash (is Docker running?). Nothing changed."; exit 1 ;;
esac

umask 077
touch .env
{ grep -v '^OBSERVE_PASSWORD_HASH=' .env; printf "OBSERVE_PASSWORD_HASH='%s'\n" "$hash"; } > .env.new \
  && mv .env.new .env && chmod 600 .env || { rm -f .env.new; echo "Couldn't write .env. Nothing changed."; exit 1; }
echo "Saved. Starting the dashboards..."
docker compose --profile observe up -d || exit 1
host=$(hostname)
echo "Done. Open http://$host.local:19999 (metrics) or http://$host.local:9080 (logs) and sign in as admin."
