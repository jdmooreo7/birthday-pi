# Birthday Pi: build plan for the first usability release

**Status:** Draft for Product Owner review · **Written:** 2026-10-14 · **Release name:** v0.1 "first test"

The goal is a build that a real family can use for 2–3 weeks at home, so we can watch how Grandma and visiting family use it. Screens follow the mockup canvas "Birthday Pi v1 screens". Decisions are in `product-decisions.md`.

## What's in it
1. **First-run setup.** The monitor shows a welcome card with a QR code. A family member's phone opens setup, Grandma picks her 4-digit PIN, and the family adds people.
2. **People and dates by hand.** Name, birthday (month and day; year optional), and anniversaries between two people. A "who's missing a birthday" list.
3. **Reminders.** Gift reminder at 2 weeks, card at 1 week, call on the day, for birthdays and anniversaries. The text grows 16 px a day from 64 px to a 160 px maximum. Several reminders stack, soonest first, and share the screen. "Got it" needs no PIN and clears the reminder on every screen.
4. **Devices know who's using them.** Each phone or tablet picks a name once. Choosing Grandma asks for the PIN once and then trusts that device. The monitor always asks for the PIN.
5. **Photos.** Upload from a phone, including iPhone HEIC photos. Tag who's in a photo by hand. Grandma's own uploads show straight away; everyone else's wait for her OK. She can hide any photo later.
6. **Slideshow.** After 5 minutes idle, photos cycle at 1 per minute. On someone's day only photos tagged with them show. Night dimming from 10pm to 5am, and any input or new reminder brightens the screen. This already works in the placeholder.
7. **PIN reset** with a command run on the Pi.
8. **Install** with one `docker compose up -d`, plus the optional kiosk script.

## What's not in it
- Face recognition. It comes in the second test build, which adds a separate worker container. Hand tagging covers the "only their photos on their day" rule until then.
- Integrations, phone alerts and text messages (see `features/`).
- Pets, accounts and passwords, and access from outside the home.

## How it's built (Tech Lead)

| Part | Choice | Why |
|---|---|---|
| App | One Python container: FastAPI, server-rendered HTML pages, a little plain JavaScript, no front-end build step | Small and easy to read. Python matches the face-recognition spike, so build 2 reuses the same language. |
| Data | SQLite file plus photo folders in `./data` on the Pi, mounted into the container | No database server. Back up by copying one folder. |
| Photos | Resized to screen size on upload (Pillow, with `pillow-heif` for HEIC), plus a thumbnail. Originals are not kept. | About 0.5 GB per 1,000 photos. |
| Screens | `/screen` for the monitor, `/` for phones. Both check for changes every 10 seconds. | "Got it" on a phone clears the monitor within seconds. Simpler and more robust than a live connection. |
| Device identity | A long-lived random cookie per device, linked to a person. A "trusted as Grandma" flag is set only after the PIN is entered. The `/screen` page is never trusted. | No accounts. Clearing the browser just asks "Who's this?" again. |
| PIN | Stored hashed (scrypt). Locks for 1 minute after 5 wrong tries. | Keeps a curious grandchild from guessing it. |
| Time | The container uses the Pi's time zone | "Today" must match Grandma's clock. |
| Port | 8080, at `birthdaypi.local:8080` | Same as now. It replaces the placeholder container. |

**Resource budget:** the app container is capped at 256 MB (expected under 120 MB). Chromium in kiosk mode on the Pi uses about 400–600 MB. That leaves more than 2.5 GB free for build 2's face worker. On disk, the image is about 200 MB and 2,000 photos about 1 GB. Uploads are refused when free disk falls below 2 GB.

**Security:** reachable on the home Wi-Fi only, with no port forwarding. Cookies are `SameSite=Strict`. Uploads are limited to 25 MB per file and to image types. The container runs as a non-root user.

## Testing aid: "pretend today is"
Reminders depend on the date, so waiting two weeks to test the card reminder isn't practical. A hidden settings switch (PIN-protected) sets a pretend date. It shows a visible banner while it's on so nobody forgets. We'll also have a sample family with fake people and drawn photos for demos and for testing before real data goes in.

## Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | App skeleton replaces the placeholder | `docker compose up -d` on the Pi serves `/screen` and `/` from the new container. The kiosk shows it, and memory stays under the cap. |
| M1 | Setup, people and dates, PIN | A family member can set up a fresh Pi from their phone using the welcome QR. Grandma's PIN works, and the reset command works. |
| M2 | Reminders | All three reminder types appear on the right days, grow, stack and clear everywhere, checked with "pretend today is". |
| M3 | Photos and slideshow | Upload, tagging, approval on the monitor and on a trusted phone, hiding, and the celebration-day slideshow all work with HEIC photos from an iPhone. |
| M4 | Release v0.1 | Fresh install on a newly flashed Pi following only the README works. 24-hour soak on the Pi with no restarts or memory growth. Tagged `v0.1.0` on GitHub. |

## Usability test (Product Manager)
- **Who:** Grandma, plus 2–3 family members who visit her.
- **Tasks to watch:** set up the Pi from scratch; add a birthday; upload photos as a visitor; Grandma approves them on the monitor and on her phone; acknowledge a reminder; hide a photo.
- **What to learn:** where people hesitate, whether reminders are noticed and readable from across the room, whether the PIN feels like a hurdle, and whether anyone misses face recognition.
- **When:** the Product Owner runs a short usability check at the end of every milestone (M1 to M4), then the full test after v0.1. Tests start with the sample family.
- **How:** watch the first session in person; after that, a short check-in each week. The app keeps a simple local log of "Got it" times, which tells us how quickly reminders get noticed. It stays on the Pi.

## Risks
- **iPhone HEIC support on ARM** may need extra packages in the image. Check this in M0.
- **Chromium memory on a 4 GB Pi** over many days. The M4 soak test covers this.
- **The "trusted as Grandma" cookie** could be cleared by browser privacy settings, and iPhone Safari clears website data after long periods of not visiting. If that happens she just enters her PIN again.
- **Family photos of children.** Get the family's OK before testing with real photos.

## Questions for the Product Owner
1. ~~Who are the test participants?~~ For milestone checks the Product Owner plays Grandma, and other devices (e.g. the Mac) play other family members.
