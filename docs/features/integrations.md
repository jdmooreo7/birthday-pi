# Future feature: integrations

**Status:** Parked for consideration after v1 · **Logged:** 2026-10-14 · **Owner:** Product Owner

## Why it's parked
Storyboard pillar 5 says Birthday Pi grows by connecting to other tools, not by adding steps. Every integration needs the internet, and v1 promises that nothing needs the internet after setup. So v1 ships with no integrations. Later ones should be optional add-ons that the family turns on.

## Candidates

| Integration | What it does | Notes |
|---|---|---|
| Calendar import (Google, iCloud) | Pulls family birthdays and anniversaries in | Saves typing during onboarding; needs an account sign-in |
| Phone contacts import | Reads birthdays already saved in contacts | Could be a one-time file export (vCard) instead, which avoids the internet |
| Shared family album (Google Photos, iCloud) | New photos flow into the approval queue | Grandma still approves every photo |
| Family chat nudge | Posts "Call Grandma's grandson today" to the family chat | Overlaps with `future-reminders-beyond-monitor.md` |
| Smart speaker or display | Reads reminders aloud | Cloud integration; high setup burden |

## Questions for the Product Owner
1. Is a one-time file import (vCard, `.ics`) acceptable in v1 since it needs no internet?
2. Which integration would save the family the most effort?

## Design constraints to keep
- Off by default; turning one on takes one step.
- Birthday Pi keeps working fully when the integration or the internet is down.
- No integration bypasses Grandma's photo approval.
