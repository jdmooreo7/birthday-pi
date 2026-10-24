#!/bin/sh
# Update Birthday Pi, and go back to the previous version by itself if it isn't healthy afterwards.
# Run on the Pi from ~/birthday-pi:
#   scripts/update.sh          pull the latest of the current branch
#   scripts/update.sh v0.3.0   switch to a release tag
set -u
cd "$(dirname "$0")/.." || exit 1

# Keep the dashboards if they're running.
profile=""
[ -n "$(docker compose --profile observe ps -q netdata 2>/dev/null)" ] && profile="--profile observe"

# The version and build date the app shows on Settings and Help.
up() {
  BIRTHDAY_PI_VERSION=$(git describe --tags --always) BIRTHDAY_PI_BUILT=$(date +%F) \
    docker compose $profile up -d --build
}

healthy() {  # wait up to 3 minutes for the app and the face worker to report healthy
  i=0
  while [ $i -lt 36 ]; do
    a=$(docker inspect -f '{{.State.Health.Status}}' birthday-pi-app-1 2>/dev/null)
    f=$(docker inspect -f '{{.State.Health.Status}}' birthday-pi-faces-1 2>/dev/null)
    [ "$a" = healthy ] && [ "$f" = healthy ] && return 0
    i=$((i + 1)); sleep 5
  done
  return 1
}

scripts/diag.sh  # the update recreates the containers, which loses their logs
prev=$(git rev-parse HEAD)
echo "Now on $(git describe --tags --always)."

if [ $# -gt 0 ]; then
  git fetch --tags && git checkout --detach "$1" || { echo "Couldn't get $1. Nothing changed."; exit 1; }
else
  git pull --ff-only || { echo "Couldn't get the update. Nothing changed."; exit 1; }
fi
[ "$(git rev-parse HEAD)" = "$prev" ] && { echo "Already up to date."; exit 0; }

if up && healthy; then
  echo "Updated to $(git describe --tags --always). Everything is healthy."
  # Clear build leftovers older than a week and images nothing uses. Never touches data or tagged images.
  docker builder prune -f --filter until=168h >/dev/null
  docker image prune -f >/dev/null
  exit 0
fi

echo "Not healthy after the update. Going back to $prev."
scripts/diag.sh
git checkout --detach "$prev" && up && healthy && echo "Back on the previous version. Everything is healthy." && exit 1
echo "Still not healthy on the previous version. Don't unplug it; ask for help."
exit 2
