# Birthday Pi: fresh install tester checklist

Thank you for testing. We want to know whether someone new can install Birthday Pi on their own Raspberry Pi using only the [README](../README.md). **Please don't ask us for help along the way.** Where you get stuck is exactly what we need to learn. Write it down, work it out if you can, and keep going.

**Time:** about 1 to 1½ hours, most of it waiting for downloads.

## Before you start
- [ ] A Raspberry Pi 5 (4 GB is ideal) with power supply, and a microSD card of 32 GB or more that **you're happy to erase**
- [ ] Another computer to flash the card and to SSH from
- [ ] Your home Wi-Fi name and password
- [ ] A phone on the same Wi-Fi
- [ ] Optional: a monitor and mouse for the Pi, if you want to try the full-screen kiosk
- [ ] Something to note times and problems (the report template is at the bottom)

## Part 1: Install (follow the README)
Note the time you start and finish each step, and anything that confused you.

| Step | README section | You're done when… | Start | End |
|---|---|---|---|---|
| 1 | **Step 0: Set up the Pi** | You can SSH into the Pi | | |
| 2 | **Step 1: Install the tools** | `docker run --rm hello-world` prints "Hello from Docker!" | | |
| 3 | **Step 2: Get Birthday Pi and start it** | `docker compose up -d` finishes without errors | | |
| 4 | **Step 3: See it** | A page from the Pi opens in your phone's browser | | |
| 5 | Optional: **kiosk** | After a reboot, the Pi's monitor shows Birthday Pi full-screen | | |

**Watch for:** the setup QR code on the monitor points to `birthdaypi.local`. If you gave your Pi a different hostname in Step 0, the README explains how to change this. Did you notice that part, and did it work?

## Part 2: Try it (about 15 minutes)
Pretend you're setting this up for a grandparent. Use your phone.

- [ ] Open `http://<your-pi>:8080/` and go through setup. Choose a name for "Grandma" and a 4-digit PIN.
- [ ] Choose **Grandma** on "Who's using this phone?" and enter the PIN.
- [ ] Add 3 people with birthdays. Give one a birthday within the next 2 weeks.
- [ ] Add a wedding or graduation anniversary to one of them.
- [ ] Check the monitor, or `http://<your-pi>:8080/screen` in a browser: does a reminder appear for the birthday that's coming soon? Tap **Got it**.
- [ ] Add 2 or 3 photos from your phone, then find them under **Photos**.
- [ ] On another device (a laptop or a second phone), choose **Someone new**, add a photo, then approve it as Grandma.

## Part 3: Tell us
Please copy this into a [GitHub issue](https://github.com/jdmooreo7/birthday-pi/issues/new) titled "Fresh install report", or send it to whoever asked you to test.

```
Pi model and RAM:
SD card size:
Raspberry Pi OS version (with desktop / Lite):
Used the kiosk? (yes/no):

Time per step (minutes):  Step 0:   Step 1:   Step 2:   Step 3:   Kiosk:
Total time:

Where did you get stuck or have to guess? (step, what happened, what you did)
-

Any error messages? (paste them exactly)
-

Anything in the README that was wrong, missing or unclear?
-

Part 2: anything confusing or broken?
-

One thing you'd change:
-

Would you set this up for someone in your family? (yes / maybe / no, and why)
```

## Afterwards: remove it (optional)
From `~/birthday-pi` on the Pi:
```sh
docker compose down -v        # stops Birthday Pi and deletes its data, including any photos you added
rm ~/.config/autostart/birthday-pi-kiosk.desktop   # only if you set up the kiosk
```
Or just re-flash the SD card.

Your photos and names never left your Pi. Birthday Pi doesn't send anything to the internet.
