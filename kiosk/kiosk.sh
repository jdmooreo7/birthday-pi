#!/bin/sh
# Launch Chromium full-screen on the Pi's monitor, showing the Birthday Pi screen.
URL="${BIRTHDAY_PI_URL:-http://localhost:8080/}"

# Wait up to 2 minutes for the web container to answer after boot.
i=0
while [ $i -lt 60 ] && ! curl -fsS -o /dev/null "$URL"; do
  i=$((i + 1)); sleep 2
done

exec chromium \
  --kiosk "$URL" \
  --ozone-platform=wayland \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --password-store=basic \
  --check-for-update-interval=31536000
