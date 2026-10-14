# Birthday Pi

A small, local-only family reminder screen for a Raspberry Pi 5. It runs in Docker on your home network and shows birthdays and reminders on a monitor.

> **Status:** early. Right now this repo has a placeholder screen, a monitor kiosk script, and the design docs. The real app is still being built. See [`docs/birthday_pi_storyboard.html`](docs/birthday_pi_storyboard.html) for the plan and [`docs/product-decisions.md`](docs/product-decisions.md) for decisions so far.

## What you need
- Raspberry Pi 5 (4 GB RAM), 32 GB SD card, 64-bit Raspberry Pi OS (Debian trixie)
- A monitor (HDMI) if you want the kiosk screen
- [Docker Engine and Compose](https://docs.docker.com/engine/install/debian/)

Everything runs on your home network. Nothing needs the internet after setup.

## Quick start
```sh
git clone https://github.com/jdmooreo7/birthday-pi.git ~/birthday-pi
cd ~/birthday-pi/placeholder
docker compose up -d
```
Then open `http://<your-pi-address>:8080/` from any device on your network.

## Optional: full-screen kiosk on the Pi's monitor
The kiosk starts Chromium full-screen at `http://localhost:8080/` when the desktop logs in.
```sh
chmod +x ~/birthday-pi/kiosk/kiosk.sh
mkdir -p ~/.config/autostart
cp ~/birthday-pi/kiosk/birthday-pi-kiosk.desktop ~/.config/autostart/
```
This assumes the repo is cloned at `~/birthday-pi` and the Pi boots to a desktop with auto-login. Set `BIRTHDAY_PI_URL` to point the kiosk somewhere else.

## Your photos stay yours
Real family photos and face data are never committed (see `.gitignore`). Put your own photos in `placeholder/photos/` on the Pi only.

## License
[MIT](LICENSE)
<!-- branch ruleset test -->
