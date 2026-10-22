# Birthday Pi: M8 pilot plan (v0.3 "Grandma pilot")

**Status:** Planning (M8 started 2026-10-15) · **Written:** 2026-10-15 · **Release:** v0.3 (M8 pilot, M9 fixes and a 7-day soak)

M8 is the first time someone who isn't us uses Birthday Pi every day. A second Pi runs at a real Grandma's home, with her family. We watch the first session in person, then learn from a weekly check-in and from what the Pi records about itself. Decisions are logged in `product-decisions.md`.

## Prep checklist (before day one)
| # | Step | Who | Done when |
|---|---|---|---|
| 1 | Pick the 3-week window with a real birthday or anniversary in it | PO | Dates agreed with her family. **Done 2026-10-21:** from Saturday 2026-10-24, about 3 weeks to 2026-11-14, with a real birthday in it |
| 2 | Ask what phone she uses, and how old it is | PO | Model and system version known. Anything older than iOS 14.5 or Chrome 87 gets our "too old" message, and older Android phones may not open `birthdaypi.local` (then we use the Pi's address instead). **Done 2026-10-21:** iPhone on iOS 27.0.1 |
| 3 | Consent from the adults in her family, and parents for children | PO, with a one-page note from Security | Everyone has said OK before photos go in. **2026-10-21:** her family, and parents for the children in her photos, have agreed; the one-page note (draft on the design canvas) is for them to keep and sign |
| 4 | Buy the hardware (list under "The second Pi") | PO | Arrived |
| 5 | Tag `v0.2.1` after the before-pilot changes (step 10) are built and our Pi has run them cleanly for a few days | Tech Lead, SRE | Tag on `main`. **Done 2026-10-21:** `v0.2.1` at `cf8faba` after 41 hours clean on our Pi; pi2 runs the tag |
| 6 | Install it at our house **using only the README**, timed, noting every snag | PO (Tech Lead watches) | Install report filed; README fixed |
| 7 | 48-hour burn-in at our house with the sample family, then wipe it | SRE | 0 restarts; data wiped so she starts fresh. **Done 2026-10-21:** passed, wiped, pi2 on `main` |
| 8 | Printed card by the screen, and the day-one script | Designer | Approved on the design canvas |
| 9 | Pilot helpers: a numbers-only weekly check (`scripts/pilot-stats.sh`) and a safe data copy to the USB stick (`scripts/backup-data.sh`) | Tech Lead, SRE | Built and tested on our Pi 2026-10-15: the check matched the live counts, and a copy restored into a throwaway volume passed SQLite's integrity check with all 12 people, 228 photos and 223 faces |
| 10 | Before-pilot changes: no "Grandma" default (setup asks who it's for, and every page uses that name), the screen on a phone (its own icon and bookmark name, no code to scan, a "See the screen" button on her home), anniversaries become **special dates** (wedding, graduation, remembering them, or something the family names), **remembering** someone who has died (only on the day, quietly, no reminders; only she can set it), and **"Not family" can be taken back** (Undo straight after, and a "Set aside" list with "Name them after all") | Designer, Tech Lead | Approved on the design canvas, built, tested, on pi2 before day one |
| 11 | Day one next door (see below) | Everyone | She's using it |

## Goal and pass (Product Manager)
**What we want to learn:** does Grandma notice and act on reminders without being prompted, can she look after photos and faces herself, and does the Pi keep running without us?

**How long:** 3 weeks, so that at least one real birthday or anniversary reminder falls inside it. Choose the start date with that in mind.

**M8 passes when:**
1. **Reminders are noticed.** Every reminder in the 3 weeks is cleared with "Got it", most of them on the day they appear. The `reminder_acks` table already records when.
2. **She manages on her own.** She approves visitors' photos and answers "Is this Leo?" without anyone's help after week 1. We count the times she has to phone someone.
3. **It runs without us.** There's no visit to fix a fault. A power cut recovers by itself.
4. **She wants to keep it.** Asked at the end: "Would you miss it if we took it away?"

**We stop early if** it upsets her or the family, wakes anyone at night, or loses data.

**What we bring back** is a list of where people hesitated, ranked. That list becomes M9. We don't bring back names, dates or photos.

## Day one (Designer)
- **A family member sets it up with her, not for her,** following the printed setup sheet. They scan the welcome QR, type what the family calls her under "Who is this for?", she picks her PIN, and together they add 3–5 people (special dates too, if she likes). Then visitors upload a few photos from their phones and she approves them. This is the real first-run flow.
- **Not on day one (Designer, 2026-10-21):** marking someone as remembered. If the family wants it, they do it with her later, in their own time. If she taps "Not family" by mistake, the Undo strip or Set aside brings it back.
- **Before we leave (SRE, 2026-10-21):** run `scripts/backup-data.sh` to the USB stick, which stays in her house, and pull the power to check it comes back to the screen by itself.
  - The stick is labelled `BIRTHDAYPI`. pi2 doesn't mount it on its own, so first run `ssh -t winston@pi2.local 'sudo mkdir -p /media/winston/BIRTHDAYPI && sudo mount -o uid=winston,gid=winston,umask=077 /dev/sda1 /media/winston/BIRTHDAYPI'` (needs the sudo password), then `scripts/backup-data.sh /media/winston/BIRTHDAYPI`, then `sudo umount /media/winston/BIRTHDAYPI`. Tested on pi2 on 2026-10-22: the archive was written and checked.
- **The printed card** (approved 2026-10-16, five steps, the same as Help on her phone) stays by the screen, including "if the screen is blank, unplug it for 10 seconds".
- **We watch without helping.** One of us takes notes and only steps in if she's stuck for more than a minute or gets upset.
- **What we watch for:** can she read the reminder from her chair? Is the PIN a hurdle? Does she notice "N faces to check"? Does night dimming bother anyone? Does she use the monitor or her phone?
- **Her phone is how she does things (PO, 2026-10-15).** The screen is for looking at: everything she does, from "Got it" to approving photos and checking faces, happens on her phone, which already clears the screen within seconds. On day one the family member adds Birthday Pi to her phone's home screen as an icon and makes sure the phone is trusted as Grandma.
- **The screen needs no input.** A USB mouse and keyboard are our tools on visits, not hers: a pointer on a TV across the room is hard to use for someone who isn't used to computers.
- **If the screen is her smart TV,** the Pi 5 can take the TV remote's arrow and OK buttons over HDMI (HDMI-CEC; our Pi has `/dev/cec0`). Then OK could mean "Got it". But a TV is off or showing something else most of the day, so she'd miss reminders unless the Pi turns the TV on, and that is intrusive. The pilot uses a dedicated, always-on monitor (PO), and the TV remote is a v1.1 "Beyond the monitor" idea.

## The second Pi (Tech Lead)
- **Hardware:** Pi 5 (4 GB), the official 27 W power supply, a 64 GB high-endurance microSD (Samsung PRO Endurance, or SanDisk High Endurance), the official case with its fan, a micro-HDMI to HDMI cable, a USB stick for the data copies, and a dedicated monitor for her home, as on our Pi.
- **Software:** a `v0.2.1` tag (proposed): v0.2.0 plus what we deployed after the soak (evidence through a reboot, `update.sh`, the old-browser message), once it has run cleanly on our Pi for a few days. Installed **using only the README** on a freshly flashed card. That doubles as an early run of M12 (an outside install) and shows us what the README is missing. The kiosk is on.
- **Memory:** the same as our Pi: app about 65 MB, faces worker up to 768 MB while it's scanning, Chromium about 1.1 GB, and about 2.5 GB left free. The dashboards (on) add 250–350 MB of memory, 1.6 GB of disk and up to 256 MB of metrics history.
- **What we build for M8:** no new features, by design. We pilot what passed M7; anything we learn goes into M9. Only small helpers for running the pilot (see the prep checklist).

## Keeping it running (SRE)
- **Before we leave on day one:** pull the power to check it comes back to the screen by itself, and check the self-healing health checks are working.
- **Updates during the pilot:** none unless something breaks. See "When something goes wrong" below.
- **Data safety:** there's no backup feature until v1.1. On each visit we copy the data folder to a USB stick that **stays in her house**. Restoring it is the same process as our 2026-10-15 rollback.
- **Weekly check-in:** a short call or visit. On a visit we run read-only checks (container health, restarts, memory, disk, how quickly reminders were cleared) and write down only the numbers.
- **Dashboards on (PO, 2026-10-15),** with their own password that we keep, not written down in her house. Netdata and Dozzle are only reachable on her Wi-Fi, so they help on visits; between visits we rely on what the Pi keeps on disk (below).

## When something goes wrong (SRE and Tech Lead)
A reboot fixes most things. We checked what survives one on our Pi (read-only, 2026-10-15):

| Evidence | Survives a reboot? | Survives an update? |
|---|---|---|
| Family data: people, photos, faces, "Got it" times | Yes | Yes |
| Container logs (app, faces worker), 30 MB each | Yes | **No**: an update recreates the containers |
| System journal: kiosk/Chromium, out-of-memory kills, Wi-Fi drops, power warnings | **No**: Raspberry Pi OS keeps it in memory (`40-rpi-volatile-storage.conf`) | Yes, until a reboot |
| Netdata metrics | **No**: only the last hour, in memory (`observe/netdata.conf`) | No |

So the PO is right that a reboot today loses the evidence we'd need: what happened just before the Pi froze or the screen went blank.

| Option | How a fix happens | Evidence kept | Cost |
|---|---|---|---|
| A. Reboot only (unplug 10 s) | Grandma, from the printed card | Data and container logs | Nothing. We lose the cause. |
| **B. Keep the evidence through a reboot** | Same as A | Everything above, from the last 7 days | Three small changes, below |
| C. A family member runs an update | `scripts/update.sh v0.3.x` over SSH, which saves the evidence first, then rolls back by itself if the app isn't healthy | Everything | Needs someone happy to use SSH. The script is a first step towards M10's updates. |
| D. Remote access (an outbound-only VPN such as Tailscale) | We look and fix from home | Everything, live | Reverses "no away-from-home access", adds an outside service and an account, and needs Security sign-off. Only worth it if she lives far away. |

**Decided (PO, 2026-10-15): B, after the Security Analyst's review of the logs (passed, below). C if needed: the PO runs it, since the pilot is next door. D isn't needed.**

B's changes, in the repo and tried on our Pi first:
1. **System journal on disk,** capped at 200 MB: `scripts/journald-birthday-pi.conf`, installed as `/etc/systemd/journald.conf.d/50-birthday-pi.conf`. Undo: delete it and restart journald.
2. **Netdata keeps its history on disk** in the `netdata-cache` volume: every second for 2 days, then every minute for 7 days, at most 256 MB (`observe/netdata.conf`).
3. **`scripts/diag.sh`** saves container health and restarts, memory, disk, power and temperature, the journal and the app and faces logs to `~/birthday-pi-diag/` (owner-only, newest 20 kept). Run it before every update and before a reboot when we can.

**The watchdog is already on.** Raspberry Pi OS turns on the Pi 5's hardware watchdog (`40-rpi-enable-watchdog.conf`): if the system freezes for a minute, the Pi restarts itself. It doesn't catch an app crash (the health checks do), a blank Chromium (the kiosk restart does), or a Pi that's slow but still running. With the journal on disk, we'll now see why it restarted.

### Security review of the logs (Security Analyst, 2026-10-15)
Read on our Pi with values hidden; only the shape of each line was looked at.
- **App log:** web requests only, with the phone's address on the home Wi-Fi, the page and a number or photo code (`/people/3`, `/photo-files/<code>.jpg`). No names, dates, PINs or form contents. The faces worker logs counts only.
- **System journal:** SSH logins (public key fingerprints), Wi-Fi network name and device addresses, hardware and service messages. The Wi-Fi password shows as `<hidden>`. No family data.
- **Netdata:** numbers, container and process names only.
- **Conditions:** `diag.sh` never collects `.env`, `docker inspect` settings (they hold the dashboard password hash) or `docker compose config`; its files are owner-only and stay on the Pi. Passed.

## Privacy and access (Security Analyst)
- **Her photos and face data never leave her house.** Pilot notes hold only counts and observations, no names, dates, photos or screenshots of her family.
- **Consent first:** the adults in her family say OK to face recognition before any photos go in, and parents say it for children. Remove person is the answer for anyone who'd rather not be included.
- **Network:** home Wi-Fi only, no port forwarding, no away-from-home access. She lives next door, so a fix means a visit.
- **SSH:** keys only, with a new key used just for this Pi, and password login off from the start, as on our Pi. `unattended-upgrades` is on.
- **PIN:** she picks it herself, and we don't write it down. A forgotten PIN is reset with the command in the README, on a visit.
- **Accepted risk:** the PIN is sent over plain HTTP on her Wi-Fi (accepted for v1 at home). If her Wi-Fi is shared with lodgers or neighbours, we should talk about it before going ahead.

## Decided (2026-10-15)
- The pilot Grandma is someone other than the PO's own family, who lives next door; when is still to be chosen.
- A dedicated, always-on monitor, as on our Pi.
- Option B to keep evidence through a reboot; C (an update run by the PO) if needed; no remote access.
- The pilot runs a `v0.2.1` tag; the two pilot helpers and the README step for keeping the log through a restart are built.
- Her phone is how she does things; the screen needs no input.
- Dashboards are on for the pilot.

## Questions for the Product Owner
1. **When:** a 3-week window with a real birthday in it.
2. **Hardware:** do we buy a second Pi kit and monitor, or use ones she already has?
3. **Her phone:** which phone and how old (prep step 2)?

## M9 (after the pilot)
Fix the ranked list from M8, deploy to both Pis, then run a 7-day soak on her Pi. Tag `v0.3.0`.
