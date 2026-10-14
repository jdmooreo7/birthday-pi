# Future feature: text notification for photo approval

**Status:** Parked for consideration after v1 · **Logged:** 2026-10-14 · **Owner:** Product Owner

## The idea
When someone adds photos, Grandma gets a text message with a link to Birthday Pi's approval page. She taps it, enters her PIN, and approves or rejects the photos.

## Why it's parked
In v1 Grandma approves on the monitor or on her phone or tablet browser, protected by a 4-digit PIN. Sending a text means the Pi has to reach an SMS provider over the internet, which v1 avoids.

## Things to work out
- **Sending:** an SMS provider (account, cost, credentials kept on the Pi) or an alternative such as email, ntfy or a family-chat message (see `future-reminders-beyond-monitor.md` and `integrations.md`).
- **The link only works at home:** Birthday Pi can't be reached from outside her Wi-Fi, so the message should say so ("Open this when you're home").
- **Batching:** one text per upload session, not per photo, and quiet hours (no texts 10pm to 5am).
- **Link safety:** the link should not skip the PIN.
