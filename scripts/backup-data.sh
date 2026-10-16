#!/bin/sh
# Copy Birthday Pi's data (people, dates, photos, faces) to a USB stick, safely while it's running.
# Run on the Pi from ~/birthday-pi:  scripts/backup-data.sh /media/winston/<stick name>
# Writes birthday-pi-data-<date>.tar.gz on the stick and keeps the newest 4.
# The stick holds family photos and face data and isn't encrypted: keep it in the house, like a key.
#
# To restore onto a Pi: docker compose down; then
#   docker run --rm -v birthday-pi_data:/data -v /media/winston/<stick>:/in birthday-pi:local \
#     sh -c 'rm -rf /data/* && tar -xzf /in/<file> -C / && rm -f /data/birthday-pi.db-wal /data/birthday-pi.db-shm \
#       && mv /data/tmp/backup.db /data/birthday-pi.db'
# and docker compose up -d.
set -u
dest=${1:-}
[ -n "$dest" ] && [ -d "$dest" ] && [ -w "$dest" ] || { echo "Give the stick's folder, e.g. scripts/backup-data.sh /media/winston/STICK"; exit 1; }
out="$dest/birthday-pi-data-$(date +%Y%m%d-%H%M%S).tar.gz"

# A consistent copy of the database first (SQLite's own backup, safe while the app is writing).
docker exec birthday-pi-app-1 python -c '
import sqlite3
src = sqlite3.connect("/data/birthday-pi.db"); dst = sqlite3.connect("/data/tmp/backup.db")
src.backup(dst); dst.close(); src.close()' || { echo "Couldn't copy the database. Nothing saved."; exit 1; }

umask 077
if docker cp birthday-pi-app-1:/data - | gzip > "$out.part" && mv "$out.part" "$out"; then
  docker exec birthday-pi-app-1 rm -f /data/tmp/backup.db
  ls -1t "$dest"/birthday-pi-data-*.tar.gz | tail -n +5 | while read -r old; do rm -f "$old"; done
  sync
  echo "Saved $out ($(du -h "$out" | cut -f1)). Wait a few seconds before unplugging the stick."
else
  rm -f "$out.part"; docker exec birthday-pi-app-1 rm -f /data/tmp/backup.db
  echo "The copy failed (is the stick full?). Nothing saved."; exit 1
fi
