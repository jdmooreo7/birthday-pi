# Birthday Pi: product decisions

Decisions made by the Product Owner, newest last. The storyboard (`birthday_pi_storyboard.html`) holds the overall concept.

| Date | Decision |
|---|---|
| 2026-10-13 | v1 reminders show on the monitor plugged into the Pi. Phone and tablet alerts are parked (`features/future-reminders-beyond-monitor.md`). |
| 2026-10-13 | The monitor is used with a mouse for now; a touchscreen is available later, so every interaction must work by touch too. |
| 2026-10-13 | After 5 minutes without input, the screen cycles through photos. |
| 2026-10-13 | From 10pm to 5am the screen goes 85% dark while idle. Touch, click or mouse movement brightens it. |
| 2026-10-13 | A new reminder brightens the screen. |
| 2026-10-13 | Each photo stays up for 1 minute. |
| 2026-10-13 | On a person's celebration day, the slideshow shows only that person's photos. |
| 2026-10-13 | On days without a celebration, the slideshow cycles through all photos on the Pi, including every person's photos. No lead-up mixing before someone's day. |
| 2026-10-13 | Photo-first onboarding with on-device face recognition is in v1 (`features/photo-first-onboarding.md`). |
| 2026-10-13 | A person is confirmed from at least 3 photos. The Pi never auto-identifies anyone with fewer than 3 verified photos; until then it asks. |
| 2026-10-13 | Tagging "who's in this photo" by hand is an acceptable fallback when face recognition misses or is wrong. Hand-tagged faces count as verified. |
| 2026-10-13 | Pets detected as faces are handled with a "Not a person" button on the "Who is this?" card, plus the 3-photo rule. No automatic pet filter in v1. Pets with birthdays are a future idea (`features/pets-as-family.md`). |
| 2026-10-13 | A one-command `setup.sh` (installs git and Docker, adds the user to the docker group, clones and starts the app) is parked on the backlog. For now the README documents the prerequisites step by step. |
| 2026-10-14 | Anyone in the home can add photos. A photo is only displayed after Grandma approves it. |
| 2026-10-14 | The monitor is the main screen. Any browser on the home Wi-Fi (e.g. Grandma's phone or tablet) can open the same display. |
| 2026-10-14 | No "upcoming" photo window: photos follow the slideshow rules above (all photos, or only the celebrated person's on their day). Storyboard updated. |
| 2026-10-14 | Reminder text grows daily up to a maximum size; the growth curve is a design call. Two or more active reminders stack vertically, soonest celebration on top. |
| 2026-10-14 | Integrations are not in v1. They're a future feature (`features/integrations.md`). |
| 2026-10-14 | Grandma can approve photos on the monitor and on her phone or tablet browser. A text message with an approval link is a future feature (`features/photo-approval-text-notification.md`). |
| 2026-10-14 | v1 protects photo approval with a 4-digit PIN. |
| 2026-10-14 | First usability release covers the core loop: add people and dates by hand, reminders with "Got it", photo upload with Grandma's PIN approval, and the slideshow. Face recognition follows in a second test build. |
| 2026-10-14 | Grandma picks her 4-digit PIN during first setup. A forgotten PIN is reset with a command run on the Pi by a family member. |
| 2026-10-14 | "Got it" on a reminder never needs the PIN. |
| 2026-10-14 | The Pi's hostname is `birthdaypi`, so it's reachable at `birthdaypi.local`. |
| 2026-10-14 | Each device picks "Who's this?" from the family list once (no accounts). Choosing Grandma asks for her PIN once; that device is then trusted as Grandma: her uploads show straight away and she approves without the PIN. The shared monitor always asks for the PIN. |
| 2026-10-14 | Grandma can hide any approved photo later. |
| 2026-10-14 | Usability testing starts with the sample family, not real family data. |
| 2026-10-14 | The Product Owner runs a short usability check at the end of every milestone, starting with M1 (M0's skeleton is built as part of M1). |
| 2026-10-14 | "Coming up" (phone and monitor) only lists celebrations in the next 60 days. |
| 2026-10-14 | An anniversary belongs to one person and has a type, starting with Wedding and Graduation. No "with" partner. A person can have more than one. |
| 2026-10-14 | Anniversaries can be dated up to 10 years ahead (e.g. a graduation in 2028); one shows as "Graduation day" on the date itself and as an anniversary afterwards. Birthdays stay in the past. |
| 2026-10-14 | Reminder text sizes on the 1080p monitor: the gift reminder starts at 64 px, the card reminder at 96 px, and both grow 16 px a day to 160 px; the call reminder is 160 px on the day. Stacked cards are capped at 112 px (2 cards) or 88 px (3); at most 3 show, with "+N more on your phone". |
| 2026-10-14 | When a reminder stage is acknowledged, the next stage still comes (e.g. "Got it" on the gift reminder, then the card reminder at 1 week). |
| 2026-10-14 | Backlog: a "family tree that fills in" screen on Grandma's phone that shows missing birthdays at a glance (`features/family-tree-progress.md`). |
| 2026-10-14 | Photos are stored at screen size (originals not kept) with location and camera details removed. "No" on a waiting photo deletes it from the Pi. Up to 50 photos per upload, 25 MB each; uploads stop when the SD card has under 2 GB free. |
| 2026-10-14 | On the monitor, Grandma's PIN unlocks photo approval for 10 minutes or until she taps Done. |
| 2026-10-14 | The testing page also sets how long the monitor waits before photos (10 s, 30 s, 1 min, or the normal 5 min); a testing banner shows while it is shorter. |
| 2026-10-14 | M1, M2 and M3 usability checks passed. Next: M4 (fresh install, 24-hour soak, tag v0.1.0). |
| 2026-10-14 | M4 passed: outside testers installed from the README on their own Pis (install, phone view, feature tour) with no issues. The 24-hour soak was cut short at 8 hours to keep moving (33 samples: no restarts, no errors, app memory 46 → 81 MB, well under the 256 MB limit). A full soak runs again before v1. |
| 2026-10-14 | v0.2 (face recognition) is planned as M5–M7 in `build-plan-v1.md`. Faces in photos waiting for approval are only offered for naming after Grandma approves the photo. Testing uses the 20 spike photos plus about 200 family photos the Product Owner chooses, on the Pi only. The two small v0.1 fixes (remove an anniversary; a couple's wedding anniversary showing twice) go into M5. |
| 2026-10-14 | Two roles join the team: an SRE (resiliency, observability, automation, deployment) and a Security Analyst (reviews and signs off on security). See `CLAUDE.md`. |
| 2026-10-14 | Observability: Netdata (live metrics and alerts) and Dozzle (live logs) as an opt-in compose profile `observe`, behind a password gate on ports 19999 and 9080, reading Docker through a read-only proxy on a network with no internet access. Alert delivery and access from outside the home are not decided yet. |
| 2026-10-14 | Security and resiliency fixes approved: containers hardened (no capabilities, read-only, face worker has no network), face crops visible only on Grandma's trusted devices, face worker health check, kiosk restarts Chromium if it exits. After the soak: turn off SSH password login and stop rpcbind on the Pi, back up the data volume, switch the Pi to a git clone, deploy M5. |
| 2026-10-14 | Alerts stay on the Netdata dashboard for now. Sending them to us (phone or email) is future work (`features/ops-alert-notifications.md`). |
| 2026-10-14 | Self-healing containers in M5: after 3 failed health checks in a row a container stops its own main process and Docker restarts it (no extra container or Docker access). Backups are a good feature but a nice-to-have, not a must: backlog, to be thought through. `unattended-upgrades` goes into the Pi change proposal after the soak. |
| 2026-10-14 | The 2026-10-15 runbook is approved by the Product Owner after review by all five roles: stop the soak at 6am; SSH keys only; stop rpcbind; unattended-upgrades; rollback point and backup; git clone; deploy M5 and reboot; self-heal test; observability (before the import); import the 211 test photos; cleanup; M5 usability check. The family has agreed to their photos being used for testing on the Pi. |
