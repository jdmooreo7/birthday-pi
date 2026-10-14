# Birthday Pi

A small, local-only family reminder screen for a Raspberry Pi 5. It runs in Docker on your home network and shows birthdays and reminders on a monitor.

> **Status: early (milestone 3 of the first test release).** Birthday Pi can be set up from a phone, Grandma has a PIN, and the family can add people, birthdays and anniversaries. The monitor shows what's coming up and gift, card and call reminders, and family photos (approved by Grandma) cycle when it's idle. See the [build plan](docs/build-plan-v1.md). See [`docs/birthday_pi_storyboard.html`](docs/birthday_pi_storyboard.html) for the plan and [`docs/product-decisions.md`](docs/product-decisions.md) for decisions so far.
>
> Tested on a Raspberry Pi 5 (4 GB) with Raspberry Pi OS 64-bit (Debian 13 "trixie"), Docker 29 and Compose v5. Not yet tested starting from a blank SD card, so tell us if a step is missing (open an issue).

## What you need

**Hardware**
- Raspberry Pi 5 with 4 GB RAM, a power supply, and a 32 GB (or larger) microSD card
- A home Wi-Fi or Ethernet connection. Everything stays on your home network, and nothing here talks to the outside world after setup.
- Optional: a monitor and mouse (HDMI) if you want the full-screen display on the Pi itself. You can also just open the page from a laptop or phone on the same network.

**Software and skills**
- Raspberry Pi OS **64-bit** (Debian 13 "trixie"). Use the version *with desktop* if you want the monitor kiosk; the Lite version is fine if you'll only view the page from another device.
- You'll type a few commands in a terminal. You don't need to know Linux; just copy and paste the blocks below, one at a time.

## Step 0: Set up the Pi (skip if it's already running)

1. On another computer, install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) and write **Raspberry Pi OS (64-bit)** to the SD card.
2. In Imager's settings, set the hostname to **`birthdaypi`** (recommended; it's the address Birthday Pi shows to phones by default), a username and password, your Wi-Fi name and password, and **enable SSH**. This saves you from needing a keyboard and monitor for setup.
3. Put the card in the Pi, power it on, and give it a minute or two to boot.
4. Open a terminal **on the Pi**, or connect from your computer:
   ```sh
   ssh <your-username>@<your-hostname>.local
   ```
   (Use whatever username and hostname you chose in Imager.)

Every command from here on is run **on the Pi**.

## Step 1: Install the tools (git and Docker)

A fresh Pi doesn't have Docker, and sometimes not git either. This installs both. It follows [Docker's official instructions for Debian](https://docs.docker.com/engine/install/debian/); if anything below looks out of date, that page is the source of truth.

```sh
# git, plus what Docker's installer needs
sudo apt update
sudo apt install -y git ca-certificates curl

# Add Docker's package source
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<SOURCES
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES

# Install Docker and Docker Compose
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Now let your user run Docker without `sudo`, then **log out and back in** (or reboot) so it takes effect:

```sh
sudo usermod -aG docker $USER
```

After logging back in, check that it worked:

```sh
docker --version
docker compose version
docker run --rm hello-world
```

If the last command prints "Hello from Docker!", you're ready. If you see `permission denied`, you haven't logged out and back in yet.

## Step 2: Get Birthday Pi and start it

```sh
git clone https://github.com/jdmooreo7/birthday-pi.git ~/birthday-pi
cd ~/birthday-pi
docker compose up -d
```

The first run builds the app, which takes a few minutes on a Pi. Docker starts it again automatically whenever the Pi reboots.

### Tell Birthday Pi its address

The monitor tells phones where to go: the setup QR code before setup, and the line "Add birthdays from a phone: …" afterwards. Both come from one setting, `BIRTHDAY_PI_URL`, which defaults to `http://birthdaypi.local:8080`.

**If your Pi's hostname is `birthdaypi` and you kept port 8080, you can skip this.** Otherwise (check with `hostname`), set it once and restart:

```sh
cd ~/birthday-pi
echo "BIRTHDAY_PI_URL=http://$(hostname).local:8080" > .env
docker compose up -d
```

Check it worked: `docker compose exec app printenv BIRTHDAY_PI_URL`.

- Use the form `http://<name-or-address>:<port>`, with no `/` at the end.
- If you changed the port in `compose.yaml`, use that port here too.
- If a phone can't open the `.local` address (some Android phones can't), use the Pi's IP address instead, for example `BIRTHDAY_PI_URL=http://192.168.1.50:8080`. Reserve that address for the Pi in your router's settings (often called a "DHCP reservation") so it doesn't change.

## Step 3: See it

Find your Pi's address:

```sh
hostname -I
```

Then, from any phone or computer **on the same home network**, open `http://<that-address>:8080/`. For example `http://192.168.1.50:8080/`. You can also use `http://<your-hostname>.local:8080/` on most networks.

- **On a phone:** the first visit opens setup. Type what the family calls Grandma and have her choose a 4-digit PIN. Then each person picks their name once on their own phone, and you add the family.
- **The monitor screen** is at `/screen` (the kiosk below opens it). Before setup it shows a QR code to scan; after setup it shows the clock and who's coming up.
- **Just trying it out?** Load a sample family instead of doing setup (only on a fresh install): `docker compose exec app python -m birthday_pi.cli load-sample`. Grandma's PIN is then `1234`.

## Optional: show it full-screen on the Pi's monitor (kiosk)

This needs **Raspberry Pi OS with desktop**, a monitor, and the Pi set to log in to the desktop automatically (run `sudo raspi-config`, then System Options, then Boot / Auto Login, then Desktop Autologin). Chromium comes with the desktop version.

```sh
chmod +x ~/birthday-pi/kiosk/kiosk.sh
mkdir -p ~/.config/autostart
cp ~/birthday-pi/kiosk/birthday-pi-kiosk.desktop ~/.config/autostart/
sudo reboot
```

When the Pi comes back up, it opens Birthday Pi full-screen. This assumes the repo is at `~/birthday-pi`. The kiosk always opens `http://localhost:8080/screen` on the Pi itself, so it doesn't need the `.env` setting above (if you changed the port, edit it in `kiosk/kiosk.sh`). To turn the kiosk off, delete `~/.config/autostart/birthday-pi-kiosk.desktop`.

## Optional: enforce the memory limit

The compose file caps the app container at 256 MB. On a stock Raspberry Pi OS the kernel's memory controller is off, so Docker may print a warning that the limit isn't enforced. The app still runs. To enforce it, add `cgroup_enable=memory` to the end of the **single line** in `/boot/firmware/cmdline.txt` and reboot. This edits a boot file, so make a backup first and skip it if you're not comfortable:

```sh
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
sudo nano /boot/firmware/cmdline.txt     # add " cgroup_enable=memory" at the end of the line
sudo reboot
```

If the Pi doesn't boot, put the SD card in another computer and rename `cmdline.txt.bak` back to `cmdline.txt`.

## Everyday commands

Run these from `~/birthday-pi`:

| Do this | Command |
|---|---|
| See what's running | `docker compose ps` |
| Stop it | `docker compose down` |
| Start it again | `docker compose up -d` |
| Update to the latest version | `git pull`, then `docker compose up -d --build` |
| Grandma forgot her PIN | `docker compose exec app python -m birthday_pi.cli reset-pin` (her phones will ask for the new PIN) |

## Troubleshooting

- **`permission denied` running docker:** log out and back in after `usermod`, or reboot.
- **Page won't load:** make sure your phone or computer is on the same Wi-Fi as the Pi, and check `docker compose ps` shows the container as `running`.
- **"port is already allocated" or "address already in use":** something else on the Pi is using port 8080. Change `"8080:8080"` in `compose.yaml` to another port, such as `"8081:8080"`, and use that port in the address, in `BIRTHDAY_PI_URL` (see Step 2) and in `kiosk/kiosk.sh`.
- **The address or QR code on the monitor doesn't work on a phone:** set `BIRTHDAY_PI_URL` to match your Pi (see "Tell Birthday Pi its address" in Step 2). Try the Pi's IP address if the `.local` name doesn't work.
- **`git: command not found`:** run `sudo apt install -y git`.

## Your photos stay yours

Names, dates and photos are kept in a Docker volume on the Pi, never in this repo. Photos are resized to screen size when they're added, and location and camera details are removed. Real family photos and face data are never committed (see `.gitignore`).

## License

[MIT](LICENSE)
