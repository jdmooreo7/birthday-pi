# Future feature: reminders beyond the monitor

**Status:** Parked for consideration after v1 · **Logged:** 2026-10-13 · **Owner:** Product Owner

## Why it's parked
Version 1 delivers reminders on the monitor plugged into the Pi. The monitor is always on, needs no setup on Grandma's phone and keeps everything on her home Wi-Fi. Her phone and tablet can still open the web page and tap "Got it". They just don't alert her.

## The gap
If Grandma isn't near the monitor, a reminder waits until she walks past it or opens the page. For the 2-week and 1-week reminders that's usually fine. For the day-of call reminder, a missed glance matters more.

## Options to evaluate later

| Option | How it works | Stays local-only? | Setup burden | Notes |
|---|---|---|---|---|
| Phone calendar subscription (ICS feed) | The Pi publishes a calendar feed. Her phone's own calendar app shows the events and alerts. | Yes, while she's home (the phone refreshes the feed over Wi-Fi) | Low: a one-time "subscribe" on her phone | Uses the phone's native alerts. "Got it" wouldn't sync back. Strong first candidate. |
| Browser push notifications | The web page asks permission and the Pi sends push alerts | Partly: browser push goes through Apple/Google push servers | High: needs HTTPS with a certificate her phone trusts, and on iPhone the site must be added to the Home Screen | Closest to "one tap clears everywhere", but the hardest to set up. |
| Self-hosted push app (e.g. ntfy) | A container on the Pi plus a companion app on her phone | Yes on Wi-Fi; away from home needs a relay | Medium: installing and subscribing in an app | Reliable alerts, but adds an app to her phone. |
| Email or SMS | The Pi sends a message through an email or SMS provider | No, needs internet and an account | Medium: account and credentials | Familiar to Grandma, but breaks "can't be reached from outside her Wi-Fi" in spirit and adds a cost. |
| Smart speaker or display | An announcement on a Google/Alexa device | No, cloud integration | High | Possibly delightful; belongs on the integrations roadmap. |

## Questions for the Product Owner
1. Does "can't be reached from outside her Wi-Fi" also forbid the Pi *sending* messages out (push, email)? Most of these options depend on that answer.
2. Should "Got it" on a phone alert clear the reminder everywhere, or is clearing it on the monitor and web page enough?
3. Which reminder needs an alert most: gift, card, or the day-of call?
4. Should these alerts go only to Grandma, or could family members opt in too ("Grandpa Joe's birthday is in 2 weeks")?

## Design constraints to keep
- Opting in should take Grandma one step at most, or be done for her by family during a visit.
- Alerts must use the same timing (2 weeks / 1 week / day of) and the same calm wording as the monitor.
- No alert should feel like a to-do list or nag. It's a reminder, not a task tracker.
