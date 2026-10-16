# Future feature: alert notifications for whoever looks after the Pi

**Status:** Backlog · **Logged:** 2026-10-14 · **Owner:** Product Owner

## Today
Netdata (compose profile `observe`) raises alerts on its dashboard only: high memory, a full disk, high temperature, an unhealthy container. Someone has to be looking at `:19999` to see them.

## The idea
Send alerts to the people looking after the Pi, so a failure is noticed even when nobody is at the monitor or the dashboard.

## Options to evaluate
| Option | Needs internet? | Notes |
|---|---|---|
| ntfy push to a phone | Yes | Netdata supports it. Free hosted server, or self-hosted. |
| Email | Yes | Needs mail credentials kept on the Pi. |
| A note on Grandma's monitor | No | Only for problems she can act on; most alerts are for the family helper, not her. |

## Things to work out
- Who gets them, and which alerts are worth waking someone for.
- Quiet hours and batching, so a flapping container doesn't send 50 messages.
- This is for the team's and helpers' Pis; families opt in, since v1 promises nothing needs the internet.
