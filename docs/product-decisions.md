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
