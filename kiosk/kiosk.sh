#!/bin/sh
# Launch Chromium full-screen on the Pi's monitor, showing the Birthday Pi screen.
URL="${BIRTHDAY_PI_SCREEN_URL:-http://localhost:8080/screen}"

# Wait up to 2 minutes for the web container to answer after boot.
i=0
while [ $i -lt 60 ] && ! curl -fsS -o /dev/null "$URL"; do
  i=$((i + 1)); sleep 2
done

# If Chromium crashes or is closed, start it again so the monitor never stays blank.
while true; do
  chromium \
    --kiosk "$URL" \
    --ozone-platform=wayland \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --no-first-run \
    --password-store=basic \
    --check-for-update-interval=31536000
  logger -t birthday-pi-kiosk "Chromium exited with status $?; restarting in 5 seconds"
  sleep 5
done
