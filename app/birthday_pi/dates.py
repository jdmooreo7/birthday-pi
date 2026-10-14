"""Birthday and anniversary dates: next occurrence, ages, and what's coming up."""
import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date

MONTHS = list(calendar.month_name)[1:]

# Anniversary types offered on the person form, in order. Keys are stored in the database.
ANNIVERSARY_TYPES = {"wedding": "Wedding", "graduation": "Graduation"}


def valid_month_day(month: int, day: int) -> bool:
    """Feb 29 is allowed: it's celebrated on Feb 28 in other years."""
    if not 1 <= month <= 12:
        return False
    return 1 <= day <= (29 if month == 2 else calendar.monthrange(2001, month)[1])


def occurrence(month: int, day: int, year: int) -> date:
    if month == 2 and day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, month, day)


def next_occurrence(month: int, day: int, today: date) -> date:
    """Today counts as the next occurrence."""
    d = occurrence(month, day, today.year)
    return d if d >= today else occurrence(month, day, today.year + 1)


def how_far(days: int) -> str:
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days < 14:
        return f"in {days} days"
    if days < 8 * 7:
        return f"in {days // 7} weeks"
    return f"in {round(days / 30.4)} months"


def short_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


@dataclass
class Celebration:
    kind: str  # "birthday" or "anniversary"
    name: str
    when: date
    days_away: int
    detail: str
    initial: str


def upcoming(conn: sqlite3.Connection, today: date, within_days: int | None = None,
             limit: int | None = None) -> list[Celebration]:
    """Birthdays and anniversaries, soonest first, optionally only those within_days from today."""
    items: list[Celebration] = []
    for p in conn.execute("SELECT * FROM people WHERE birth_month IS NOT NULL"):
        when = next_occurrence(p["birth_month"], p["birth_day"], today)
        detail = "Birthday"
        if p["birth_year"] and when.year > p["birth_year"]:
            detail = f"Birthday · turns {when.year - p['birth_year']}"
        items.append(Celebration("birthday", p["name"], when, (when - today).days, detail, p["name"][:1].upper()))
    rows = conn.execute("SELECT a.*, p.name FROM anniversaries a JOIN people p ON p.id = a.person_id")
    for a in rows:
        when = next_occurrence(a["month"], a["day"], today)
        detail = f"{ANNIVERSARY_TYPES.get(a['kind'], a['kind'].title())} anniversary"
        if a["year"] and when.year > a["year"]:
            n = when.year - a["year"]
            detail += f" · {n} year{'s' if n != 1 else ''}"
        items.append(Celebration("anniversary", a["name"], when, (when - today).days, detail, a["name"][:1].upper()))
    if within_days is not None:
        items = [c for c in items if c.days_away <= within_days]
    items.sort(key=lambda c: (c.when, c.name))
    return items[:limit] if limit else items


def missing_birthdays(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM people WHERE birth_month IS NULL ORDER BY name").fetchall()
