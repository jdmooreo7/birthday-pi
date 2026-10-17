# Birthday Pi

A small, local-only family reminder screen for a Raspberry Pi 5. It runs in Docker on your home network and shows birthdays and reminders on a monitor.

> **Status: early (v0.1 released; v0.2 milestone 5 of 7).** Birthday Pi can be set up from a phone, Grandma has a PIN, and the family can add people, birthdays and anniversaries. The monitor shows what's coming up and gift, card and call reminders, and family photos (approved by Grandma) cycle when it's idle. New in v0.2 so far: the Pi finds faces in the photos and groups them by person, ready for naming. See the [build plan](docs/build-plan-v1.md). See [`docs/birthday_pi_storyboard.html`](docs/birthday_pi_storyboard.html) for the plan and [`docs/product-decisions.md`](docs/product-decisions.md) for decisions so far.
>
> Tested on a Raspberry Pi 5 (4 GB) with Raspberry Pi OS 64-bit (Debian 13 "trixie"), Docker 29 and Compose v5. Not yet tested starting from a blank SD card, so tell us if a step is missing (open an issue).

## What you need

**Hardware**
- Raspberry Pi 5 with 4 GB RAM, the official 27 W power supply, and a **high-endurance** microSD card of 32 GB or more (we use 64 GB). Birthday Pi runs all day, every day, and constant small writes wear out ordinary cards. Good choices: Samsung PRO Endurance or SanDisk High Endurance. Buy from a store you trust; fake cards are common online.
- A home Wi-Fi or Ethernet connection. Everything stays on your home network, and nothing here talks to the outside world after setup.
- Optional: a monitor and mouse (HDMI) if you want the full-screen display on the Pi itself. You can also just open the page from a laptop or phone on the same network.

**Software and skills**
- Raspberry Pi OS **64-bit** (Debian 13 "trixie"). Use the version *with desktop* if you want the monitor kiosk; the Lite version is fine if you'll only view the page from another device.
- You'll type a few commands in a terminal. You don't need to know Linux; just copy and paste the blocks below, one at a time.

## Step 0: Set up the Pi (skip if it's already running)

1. On another computer, install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) and write **Raspberry Pi OS (64-bit)** to the SD card.
2. In Imager's settings, set the hostname to **`birthdaypi`** (recommended; it's the address Birthday Pi shows to phones by default), a username and password, your Wi-Fi name and password, and **enable SSH**. This saves you from needing a keyboard and monitor for setup.
   - **SSH:** pick *Allow public-key authentication only*. It's safer: no one on the network can guess a password. If you don't have a key yet, Imager can make one for you. Only the public key (the file ending in `.pub`) goes into Imager. Check the key box shows *your own computer's* key; Imager remembers old settings. On a Mac, `pbcopy < ~/.ssh/id_ed25519.pub` copies it so you can paste it in. If you can't log in afterwards ("Permission denied (publickey)"), the key didn't match: write the card again.
   - If keys are new to you, password login works too. Choose a strong password you don't use anywhere else.
   - Either way, keep the password you set: the Pi asks for it when you run `sudo` commands below.
3. **Wait for Imager to finish.** It writes the card and then checks it, which often takes 15–25 minutes. Don't take the card out until Imager says the write was successful; a card pulled out early won't boot.
4. Put the card in the Pi and power it on. The first start sets things up and restarts once by itself, so give it about 5 minutes before you connect. If `ssh` says "Connection refused" or can't find the Pi, it's still starting: wait a minute and try again.
5. Open a terminal **on the Pi**, or connect from your computer:
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

Now let your user run Docker without `sudo`:

```sh
sudo usermod -aG docker $USER
```

Then turn on memory limits, so one container that misbehaves can't use up all the Pi's memory and freeze the screen. Raspberry Pi OS ships with them off. This adds `cgroup_enable=memory` to the end of the single line in a boot file, keeps a backup, and restarts the Pi (which also lets the Docker change above take effect):

```sh
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
grep -q cgroup_enable=memory /boot/firmware/cmdline.txt || sudo sed -i '$ s/$/ cgroup_enable=memory/' /boot/firmware/cmdline.txt
sudo reboot
```

If the Pi doesn't start again, put the SD card in another computer and rename `cmdline.txt.bak` back to `cmdline.txt`. If you skip this step, Birthday Pi still runs, but Docker will say *Your kernel does not support memory limit* when it starts. If you turn them on later, after Birthday Pi is already running, restart the Pi and then run `docker compose up -d --force-recreate` from `~/birthday-pi`; containers made before keep running without limits.

When the Pi is back up (about a minute), connect again and check that it all worked:

```sh
docker --version
docker compose version
docker run --rm hello-world
```

If the last command prints "Hello from Docker!", you're ready. If you see `permission denied`, the Pi hasn't restarted yet.

## Step 2: Get Birthday Pi and start it

```sh
git clone https://github.com/jdmooreo7/birthday-pi.git ~/birthday-pi
cd ~/birthday-pi
docker compose up -d
```

The first run builds two containers, the app and the face finder, which takes several minutes on a Pi. Docker starts them again automatically whenever the Pi reboots.

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

## Optional: keep the Pi's own log through a restart

Raspberry Pi OS keeps the system log in memory, so a restart loses the clues to why the screen went blank or the Pi froze. To keep it on the SD card instead (at most 200 MB), from `~/birthday-pi`:

```sh
sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp scripts/journald-birthday-pi.conf /etc/systemd/journald.conf.d/50-birthday-pi.conf
sudo systemctl restart systemd-journald
```

To undo: `sudo rm /etc/systemd/journald.conf.d/50-birthday-pi.conf`, then `sudo systemctl restart systemd-journald`.

## Optional: watch it live (for whoever looks after the Pi)

Two dashboards show what the Pi is doing right now: **Netdata** (memory, CPU, temperature and each container, second by second, with alerts) on port 19999, and **Dozzle** (live logs from each container) on port 9080. They're off unless you turn them on, use about 250–350 MB of memory, keep 7 days of metrics on disk (at most 256 MB), and can't reach the internet. They also take about **1.6 GB of disk** for their images (Netdata alone is 1.3 GB), on top of about 0.8 GB for Birthday Pi itself, so leave room on the SD card.

Both ask for a password. Make one once, from `~/birthday-pi`:

```sh
docker run --rm -it caddy:2.11.7-alpine caddy hash-password
```

Type a password when asked. It prints a long line starting with `$2a$`. Add it to the `.env` file in `~/birthday-pi` **inside single quotes**, so the `$` signs are kept:

```sh
OBSERVE_PASSWORD_HASH='$2a$14$...the line it printed...'
```

Then start everything with the dashboards:

```sh
docker compose --profile observe up -d
```

Open `http://birthdaypi.local:19999` (metrics) or `http://birthdaypi.local:9080` (logs) and sign in as `admin` with your password. To turn them off: `docker compose --profile observe down`, then `docker compose up -d`. Turning them off doesn't free the disk space; to get it back, also run `docker image rm netdata/netdata:v2.12.0 amir20/dozzle:v11.1.3 caddy:2.11.7-alpine tecnativa/docker-socket-proxy:v0.4.2`.

## Everyday commands

Run these from `~/birthday-pi`:

| Do this | Command |
|---|---|
| See what's running | `docker compose ps` |
| Stop it | `docker compose down` |
| Start it again | `docker compose up -d` |
| Update to the latest version | `scripts/update.sh` (goes back to the previous version by itself if anything isn't healthy afterwards) |
| Copy the family's data to a USB stick | `scripts/backup-data.sh /media/$USER/<stick name>` (keeps the newest 4; the stick holds photos and faces, so keep it safe) |
| Save what's going on before a reboot, for whoever helps you | `scripts/diag.sh` (logs and numbers only, kept on the Pi in `~/birthday-pi-diag`) |
| Grandma forgot her PIN | `docker compose exec app python -m birthday_pi.cli reset-pin` (her phones will ask for the new PIN) |

## Troubleshooting

- **`permission denied` running docker:** log out and back in after `usermod`, or reboot.
- **Page won't load:** make sure your phone or computer is on the same Wi-Fi as the Pi, and check `docker compose ps` shows the container as `running`.
- **"port is already allocated" or "address already in use":** something else on the Pi is using port 8080. Change `"8080:8080"` in `compose.yaml` to another port, such as `"8081:8080"`, and use that port in the address, in `BIRTHDAY_PI_URL` (see Step 2) and in `kiosk/kiosk.sh`.
- **The address or QR code on the monitor doesn't work on a phone:** set `BIRTHDAY_PI_URL` to match your Pi (see "Tell Birthday Pi its address" in Step 2). Try the Pi's IP address if the `.local` name doesn't work.
- **`git: command not found`:** run `sudo apt install -y git`.

## Your photos stay yours

Names, dates and photos are kept in a Docker volume on the Pi, never in this repo. Photos are resized to screen size when they're added, and location and camera details are removed. Real family photos and face data are never committed (see `.gitignore`).

The face finder works out who is in each photo on the Pi itself. It runs with no network connection at all, so faces can't be sent anywhere. Removing everything (`docker compose down -v`) deletes the photos and the face data with them.

## License

[MIT](LICENSE)
