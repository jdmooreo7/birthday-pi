"""Reminders: gift 2 weeks before, card 1 week before, call on the day.

A celebration shows one reminder at a time, for the stage it's in. "Got it" acknowledges
that stage only, so the card reminder still comes later. Text grows each day a stage
goes unacknowledged, up to a maximum, and shrinks to fit when several share the monitor.
"""
import sqlite3
from dataclasses import dataclass
from datetime import date

from .dates import Celebration, how_far, upcoming

# (stage, first day it shows in days before the celebration, label, starting text size in px)
STAGES = [
    ("gift", 14, "Gift time", 64),
    ("card", 7, "Card time", 96),
    ("call", 0, "Call today", 160),
]
STEP_PX = 16
MIN_PX, MAX_PX = 64, 160
# Largest headline per card when this many reminders share the 1080p monitor.
STACK_CAP_PX = {1: 160, 2: 112, 3: 88}
MAX_ON_MONITOR = 3


@dataclass
class Reminder:
    key: str
    stage: str
    label: str
    headline: str
    sub: str
    when: date
    day: int  # 1 on the stage's first day
    size_px: int  # before fitting to the stack


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _stage(days_away: int):
    for stage in STAGES:
        name, start, _, _ = stage
        if name == "call" and days_away == 0:
            return stage
        if name != "call" and 0 < days_away <= start and days_away > _next_start(name):
            return stage
    return None


def _next_start(name: str) -> int:
    names = [s[0] for s in STAGES]
    return STAGES[names.index(name) + 1][1]


def _reminder(c: Celebration, stage) -> Reminder:
    name, start, label, start_px = stage
    day = start - c.days_away + 1
    if name == "call":
        headline = f"It's {possessive(c.name)} {c.event}"
    else:
        headline = f"{possessive(c.name)} {c.event} is {how_far(c.days_away)}"
    sub = f"{c.when.strftime('%A, %B')} {c.when.day}" + (f" · {c.extra}" if c.extra else "")
    if c.days_away == 0:
        sub = "Today" + (f" · {c.extra}" if c.extra else "")
    return Reminder(
        key=f"{c.source}:{name}:{c.when.isoformat()}", stage=name, label=label, headline=headline, sub=sub,
        when=c.when, day=day, size_px=min(MAX_PX, start_px + STEP_PX * (day - 1)),
    )


def active(conn: sqlite3.Connection, today: date) -> list[Reminder]:
    """Unacknowledged reminders, soonest celebration first."""
    acked = {r["key"] for r in conn.execute("SELECT key FROM reminder_acks")}
    result = []
    for c in upcoming(conn, today, within_days=STAGES[0][1]):
        stage = _stage(c.days_away)
        if stage:
            r = _reminder(c, stage)
            if r.key not in acked:
                result.append(r)
    return result


def monitor_sizes(reminders: list[Reminder]) -> list[int]:
    """Headline sizes in px for the reminders shown on the monitor, so the stack fits."""
    shown = reminders[:MAX_ON_MONITOR]
    cap = STACK_CAP_PX.get(len(shown), MAX_PX)
    return [max(MIN_PX, min(r.size_px, cap)) for r in shown]


def acknowledge(conn: sqlite3.Connection, key: str, person_id: int | None) -> None:
    conn.execute(
        "INSERT INTO reminder_acks (key, person_id) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, person_id)
    )
