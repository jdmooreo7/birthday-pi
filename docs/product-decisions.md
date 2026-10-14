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
