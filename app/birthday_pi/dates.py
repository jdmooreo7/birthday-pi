"""Birthdays and special dates: next occurrence, ages, and what's coming up."""
import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date

MONTHS = list(calendar.month_name)[1:]

# Special dates offered on the person form, in order: key (stored in the database) -> what the menu says.
# "remembering" is quiet: it shows only on the day, with no reminders. "other" carries the family's own name for it.
SPECIAL_DATE_TYPES = {"wedding": "Wedding anniversary", "graduation": "Graduation",
                      "remembering": "Remembering them", "other": "Something else"}
# The word for each yearly date, as in "Dana's wedding anniversary" or, on the day itself, "Dana's graduation".
_WORDS = {"wedding": "wedding", "graduation": "graduation"}


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
    kind: str  # "birthday" or "anniversary" (a special date)
    name: str
    when: date
    days_away: int
    detail: str  # e.g. "Birthday · turns 7"
    initial: str
    source: str = ""  # "p<id>" for a birthday, "a<id>" for an anniversary
    event: str = ""  # e.g. "birthday", "wedding anniversary", "graduation"
    extra: str = ""  # e.g. "turns 7", "12 years"
    person_ids: tuple[int, ...] = ()
    quiet: bool = False  # remembering someone: only on the day, no reminders, no countdown


def upcoming(conn: sqlite3.Connection, today: date, within_days: int | None = None,
             limit: int | None = None, quiet: bool = False) -> list[Celebration]:
    """Birthdays and special dates, soonest first, optionally only those within_days from today.
    Quiet ones (remembering someone) are left out unless quiet=True."""
    items: list[Celebration] = []
    for p in conn.execute("SELECT * FROM people WHERE birth_month IS NOT NULL"):
        when = next_occurrence(p["birth_month"], p["birth_day"], today)
        age = when.year - p["birth_year"] if p["birth_year"] and when.year > p["birth_year"] else None
        if p["remembered"]:
            extra = f"would have been {age}" if age else ""
            items.append(Celebration("birthday", p["name"], when, (when - today).days,
                                     "Birthday" + (f" · {extra}" if extra else ""), p["name"][:1].upper(),
                                     f"p{p['id']}", "birthday", extra, (p["id"],), quiet=True))
            continue
        extra = f"turns {age}" if age else ""
        detail = f"Birthday · {extra}" if extra else "Birthday"
        items.append(Celebration("birthday", p["name"], when, (when - today).days, detail, p["name"][:1].upper(),
                                 f"p{p['id']}", "birthday", extra, (p["id"],)))
    # People sharing the same date (a couple's wedding) celebrate once, together: "Dana & Sam".
    together: dict[tuple, list[sqlite3.Row]] = {}
    for a in conn.execute("SELECT a.*, p.name FROM anniversaries a JOIN people p ON p.id = a.person_id ORDER BY a.id"):
        together.setdefault((a["kind"], a["label"] or "", a["month"], a["day"], a["year"]), []).append(a)
    for group in together.values():
        a = group[0]
        name = " & ".join(dict.fromkeys(g["name"] for g in group))
        when = next_occurrence(a["month"], a["day"], today)
        if a["year"] and when.year < a["year"]:
            when = occurrence(a["month"], a["day"], a["year"])  # a future date: nothing to celebrate before it
        years = when.year - a["year"] if a["year"] and when.year > a["year"] else 0
        extra = f"{years} year{'s' if years != 1 else ''}" if years else ""
        remembering = a["kind"] == "remembering"
        if remembering:
            event = detail = "Remembering"
        elif a["kind"] == "other" or a["kind"] not in _WORDS:
            event = detail = a["label"] or a["kind"].title()
        else:
            word = _WORDS[a["kind"]]
            on_the_day = a["year"] and when.year == a["year"]
            event = word if on_the_day else f"{word} anniversary"  # the day itself, e.g. "graduation"
            detail = event[:1].upper() + event[1:] + (" day" if on_the_day else "")
        if extra:
            detail += f" · {extra}"
        items.append(Celebration("anniversary", name, when, (when - today).days, detail, name[:1].upper(),
                                 f"a{a['id']}", event, extra, tuple(g["person_id"] for g in group), quiet=remembering))
    if not quiet:
        items = [c for c in items if not c.quiet]
    if within_days is not None:
        items = [c for c in items if c.days_away <= within_days]
    items.sort(key=lambda c: (c.when, c.name))
    return items[:limit] if limit else items


def remembering_today(conn: sqlite3.Connection, today: date) -> list[Celebration]:
    """The quiet days that fall today: someone the family is remembering."""
    return [c for c in upcoming(conn, today, within_days=0, quiet=True) if c.quiet]


def special_date_label(kind: str, label: str | None) -> str:
    """What the family list calls a special date: "Wedding anniversary", or their own name for it."""
    if kind == "other":
        return label or "Special date"
    if kind == "graduation":
        return "Graduation anniversary"
    return SPECIAL_DATE_TYPES.get(kind, kind.title())


def missing_birthdays(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """People still needing a birthday; not someone the family is remembering."""
    return conn.execute("SELECT * FROM people WHERE birth_month IS NULL AND remembered = 0 ORDER BY name").fetchall()
