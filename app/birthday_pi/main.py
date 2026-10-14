"""Birthday Pi web app: the monitor screen (/screen) and the phone pages (everything else)."""
import hashlib
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import segno
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, devices, pins, reminders
from .dates import ANNIVERSARY_TYPES, MONTHS, how_far, missing_birthdays, short_date, upcoming, valid_month_day

HERE = Path(__file__).parent
COMING_UP_DAYS = 60  # "Coming up" lists only celebrations this many days ahead
PUBLIC_URL = os.environ.get("BIRTHDAY_PI_URL", "http://birthdaypi.local:8080").rstrip("/")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def static_url(name: str) -> str:
    """A /static link with a content hash, so browsers (and the kiosk) pick up new versions."""
    digest = hashlib.sha256((HERE / "static" / name).read_bytes()).hexdigest()[:10]
    return f"/static/{name}?v={digest}"


templates.env.globals.update(MONTHS=MONTHS, how_far=how_far, short_date=short_date, static_url=static_url)


class RedirectTo(Exception):
    def __init__(self, url: str):
        self.url = url


@app.exception_handler(RedirectTo)
async def _redirect(request: Request, exc: RedirectTo) -> RedirectResponse:
    return RedirectResponse(exc.url, status_code=303)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def today(conn: sqlite3.Connection | None = None) -> date:
    """The real date, or the "pretend today is" date set for testing."""
    if conn is not None:
        pretend = db.get_setting(conn, "pretend_date")
        if pretend:
            return date.fromisoformat(pretend)
    return date.today()


def require_setup(conn: sqlite3.Connection) -> None:
    if not db.is_set_up(conn):
        raise RedirectTo("/setup")


def require_device(conn: sqlite3.Connection, request: Request) -> sqlite3.Row:
    require_setup(conn)
    device = devices.current(conn, request)
    if device is None:
        raise RedirectTo("/who")
    return device


def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
    if "pretend" not in context:
        conn = db.connect()
        try:
            context["pretend"] = db.get_setting(conn, "pretend_date") and today(conn)
        finally:
            conn.close()
    return templates.TemplateResponse(request, name, context, status_code=status_code)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# ---------- First-run setup ----------

@app.get("/setup")
def setup_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if db.is_set_up(conn):
        return RedirectResponse("/", status_code=303)
    return page(request, "setup.html", owner_name="Grandma", errors={})


@app.post("/setup")
async def setup_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if db.is_set_up(conn):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    owner_name = str(form.get("owner_name", "")).strip()
    pin, pin2 = str(form.get("pin", "")), str(form.get("pin2", ""))
    errors = {}
    if not owner_name:
        errors["owner_name"] = "Please type what the family calls her."
    elif len(owner_name) > 40:
        errors["owner_name"] = "Please use 40 letters or fewer."
    if not pins.is_valid(pin):
        errors["pin"] = "The PIN must be exactly 4 numbers."
    elif pin != pin2:
        errors["pin2"] = "The two PINs don't match. Please try again."
    if errors:
        return page(request, "setup.html", 400, owner_name=owner_name, errors=errors)
    conn.execute("INSERT INTO people (name, is_owner) VALUES (?, 1)", (owner_name,))
    pins.set_pin(conn, pin)
    db.set_setting(conn, "setup_complete", "1")
    return RedirectResponse("/who", status_code=303)


# ---------- Who's using this phone? ----------

@app.get("/who")
def who_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    people = conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name").fetchall()
    return page(request, "who.html", people=people, device=devices.current(conn, request), error=None)


@app.post("/who")
async def who_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    form = await request.form()
    new_name = str(form.get("new_name", "")).strip()
    if new_name:
        if len(new_name) > 40:
            people = conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name").fetchall()
            return page(request, "who.html", 400, people=people, device=None, error="Please use 40 letters or fewer.")
        cur = conn.execute("INSERT INTO people (name) VALUES (?)", (new_name,))
        response = RedirectResponse(f"/people/{cur.lastrowid}?welcome=1", status_code=303)
        devices.remember(conn, request, response, cur.lastrowid, trusted_owner=False)
        return response
    try:
        person = conn.execute("SELECT * FROM people WHERE id = ?", (int(form.get("person_id", "")),)).fetchone()
    except ValueError:
        person = None
    if person is None:
        return RedirectResponse("/who", status_code=303)
    if person["is_owner"]:
        return RedirectResponse("/pin", status_code=303)
    response = RedirectResponse("/", status_code=303)
    devices.remember(conn, request, response, person["id"], trusted_owner=False)
    return response


@app.get("/pin")
def pin_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    return page(request, "pin.html", owner=db.owner(conn), error=None, locked=pins.seconds_locked(conn))


@app.post("/pin")
async def pin_check(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    form = await request.form()
    result = pins.check_pin(conn, str(form.get("pin", "")))
    if result == "ok":
        response = RedirectResponse("/", status_code=303)
        devices.remember(conn, request, response, db.owner(conn)["id"], trusted_owner=True)
        return response
    locked = pins.seconds_locked(conn)
    error = None if locked else "That PIN isn't right. Please try again."
    return page(request, "pin.html", 400, owner=db.owner(conn), error=error, locked=locked)


# ---------- Phone home and people ----------

@app.get("/")
def home(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    people_count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    now = today(conn)
    return page(
        request, "home.html", device=device, today=now, reminders=reminders.active(conn, now),
        upcoming=upcoming(conn, now, within_days=COMING_UP_DAYS), missing=missing_birthdays(conn),
        people_count=people_count, trusted_owner=devices.is_trusted_owner(device),
    )


# ---------- Reminders ----------

@app.post("/reminders/ack")
async def reminder_ack(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """ "Got it" from a phone or the monitor. No PIN needed."""
    form = await request.form()
    key = str(form.get("key", ""))
    if key in {r.key for r in reminders.active(conn, today(conn))}:
        device = devices.current(conn, request)
        reminders.acknowledge(conn, key, device["person_id"] if device else None)
    back = "/screen" if form.get("back") == "/screen" else "/"
    return RedirectResponse(back, status_code=303)


# ---------- Testing: "pretend today is" ----------

def require_trusted_owner(conn: sqlite3.Connection, request: Request) -> sqlite3.Row:
    device = require_device(conn, request)
    if not devices.is_trusted_owner(device):
        raise RedirectTo("/pin")
    return device


@app.get("/settings/date")
def pretend_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    return page(request, "pretend_date.html", device=device, real=date.today(), current=today(conn), error=None)


@app.post("/settings/date")
async def pretend_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    form = await request.form()
    if form.get("action") == "real":
        conn.execute("DELETE FROM settings WHERE key = 'pretend_date'")
        return RedirectResponse("/", status_code=303)
    try:
        chosen = date.fromisoformat(str(form.get("date", "")))
    except ValueError:
        return page(request, "pretend_date.html", 400, device=device, real=date.today(), current=today(conn),
                    error="Please pick a date.")
    db.set_setting(conn, "pretend_date", chosen.isoformat())
    return RedirectResponse("/", status_code=303)


def _people_list(conn: sqlite3.Connection) -> list[dict]:
    anns: dict[int, list[str]] = {}
    for a in conn.execute("SELECT * FROM anniversaries ORDER BY month, day"):
        label = ANNIVERSARY_TYPES.get(a["kind"], a["kind"].title())
        anns.setdefault(a["person_id"], []).append(f"{label} anniversary · {MONTHS[a['month'] - 1]} {a['day']}")
    result = []
    for p in conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name"):
        birthday = f"{MONTHS[p['birth_month'] - 1]} {p['birth_day']}" if p["birth_month"] else None
        result.append({"id": p["id"], "name": p["name"], "is_owner": p["is_owner"],
                       "birthday": birthday, "anniversaries": anns.get(p["id"], [])})
    return result


@app.get("/people")
def people_list(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return page(request, "people.html", device=device, people=_people_list(conn))


def _s(v) -> str:
    return "" if v is None else str(v)


def _form_values(conn: sqlite3.Connection, person: sqlite3.Row | None) -> dict:
    """Values for the person form. Anniversary rows are ann_<i>_kind/_month/_day/_year,
    one per saved anniversary plus one blank row for adding another."""
    values = {"name": "", "birth_month": "", "birth_day": "", "birth_year": ""}
    anns = []
    if person is not None:
        values.update(name=person["name"], birth_month=_s(person["birth_month"]),
                      birth_day=_s(person["birth_day"]), birth_year=_s(person["birth_year"]))
        anns = conn.execute("SELECT * FROM anniversaries WHERE person_id = ? ORDER BY id", (person["id"],)).fetchall()
    for i, a in enumerate(anns):
        values.update({f"ann_{i}_kind": a["kind"], f"ann_{i}_month": _s(a["month"]),
                       f"ann_{i}_day": _s(a["day"]), f"ann_{i}_year": _s(a["year"])})
    i = len(anns)
    values.update({f"ann_{i}_kind": next(iter(ANNIVERSARY_TYPES)), f"ann_{i}_month": "", f"ann_{i}_day": "", f"ann_{i}_year": ""})
    values["ann_count"] = i + 1
    return values


MAX_ANNIVERSARY_ROWS = 20
FUTURE_YEARS = 10  # anniversaries may be dated up to this many years ahead


def _parse_person_form(form) -> tuple[dict, dict, dict]:
    """Returns (values to redisplay, cleaned data, errors)."""
    try:
        count = min(max(int(form.get("ann_count", "0")), 0), MAX_ANNIVERSARY_ROWS)
    except ValueError:
        count = 0
    keys = ["name", "birth_month", "birth_day", "birth_year"]
    for i in range(count):
        keys += [f"ann_{i}_kind", f"ann_{i}_month", f"ann_{i}_day", f"ann_{i}_year"]
    values = {k: str(form.get(k, "")).strip() for k in keys}
    errors: dict[str, str] = {}
    this_year = today().year

    def to_int(key):
        try:
            return int(values[key]) if values[key] else None
        except ValueError:
            errors[key] = "Please use numbers only."
            return None

    def date_parts(prefix, max_year):
        month, day, year = to_int(f"{prefix}_month"), to_int(f"{prefix}_day"), to_int(f"{prefix}_year")
        day_key = f"{prefix}_day"
        if (month is None) != (day is None):
            errors[day_key] = "Please pick both the month and the day."
        elif month is not None and not valid_month_day(month, day):
            errors[day_key] = f"{MONTHS[month - 1] if 1 <= month <= 12 else 'That month'} doesn't have a day {day}."
        if year is not None and not 1900 <= year <= max_year:
            errors[f"{prefix}_year"] = f"Please use a year between 1900 and {max_year}."
        if year is not None and month is None:
            errors[day_key] = "Please pick the month and day too."
        return month, day, year

    clean: dict = {"name": values["name"], "anniversaries": []}
    if not values["name"]:
        errors["name"] = "Please type a name."
    elif len(values["name"]) > 40:
        errors["name"] = "Please use 40 letters or fewer."
    clean["birth_month"], clean["birth_day"], clean["birth_year"] = date_parts("birth", this_year)

    for i in range(count):
        prefix = f"ann_{i}"
        month, day, year = date_parts(prefix, this_year + FUTURE_YEARS)  # e.g. a graduation next year
        if month is None and day is None and year is None:
            continue  # a blank row, or one cleared to remove it
        kind = values[f"{prefix}_kind"]
        if kind not in ANNIVERSARY_TYPES:
            errors[f"{prefix}_kind"] = "Please pick the kind of anniversary."
        clean["anniversaries"].append((kind, month, day, year))
    values["ann_count"] = count
    return values, clean, errors


def _save_person(conn: sqlite3.Connection, person_id: int | None, c: dict) -> int:
    if person_id is None:
        person_id = conn.execute(
            "INSERT INTO people (name, birth_month, birth_day, birth_year) VALUES (?, ?, ?, ?)",
            (c["name"], c["birth_month"], c["birth_day"], c["birth_year"]),
        ).lastrowid
    else:
        conn.execute(
            "UPDATE people SET name = ?, birth_month = ?, birth_day = ?, birth_year = ? WHERE id = ?",
            (c["name"], c["birth_month"], c["birth_day"], c["birth_year"], person_id),
        )
    conn.execute("DELETE FROM anniversaries WHERE person_id = ?", (person_id,))
    conn.executemany(
        "INSERT INTO anniversaries (person_id, kind, month, day, year) VALUES (?, ?, ?, ?, ?)",
        [(person_id, *a) for a in c["anniversaries"]],
    )
    return person_id


def _person_page(request, conn, device, person, values, errors, status_code=200, welcome=False):
    return page(request, "person_form.html", status_code, device=device, person=person, values=values,
                errors=errors, welcome=welcome, this_year=today().year, ANNIVERSARY_TYPES=ANNIVERSARY_TYPES)


@app.get("/people/new")
def person_new(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return _person_page(request, conn, device, None, _form_values(conn, None), {})


@app.post("/people/new")
async def person_create(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    values, clean, errors = _parse_person_form(await request.form())
    if errors:
        return _person_page(request, conn, device, None, values, errors, 400)
    _save_person(conn, None, clean)
    return RedirectResponse("/people", status_code=303)


def _get_person(conn: sqlite3.Connection, person_id: int) -> sqlite3.Row:
    person = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    if person is None:
        raise RedirectTo("/people")
    return person


@app.get("/people/{person_id}")
def person_edit(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    person = _get_person(conn, person_id)
    welcome = request.query_params.get("welcome") == "1"
    return _person_page(request, conn, device, person, _form_values(conn, person), {}, welcome=welcome)


@app.post("/people/{person_id}")
async def person_update(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    person = _get_person(conn, person_id)
    values, clean, errors = _parse_person_form(await request.form())
    if errors:
        return _person_page(request, conn, device, person, values, errors, 400)
    _save_person(conn, person_id, clean)
    return RedirectResponse("/people", status_code=303)


@app.get("/people/{person_id}/remove")
def person_remove_confirm(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    person = _get_person(conn, person_id)
    if person["is_owner"]:
        return RedirectResponse(f"/people/{person_id}", status_code=303)
    return page(request, "person_remove.html", device=device, person=person)


@app.post("/people/{person_id}/remove")
def person_remove(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_device(conn, request)
    person = _get_person(conn, person_id)
    if not person["is_owner"]:
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
    return RedirectResponse("/people", status_code=303)


# ---------- Monitor ----------

def _screen_context(conn: sqlite3.Connection) -> dict:
    if not db.is_set_up(conn):
        qr = segno.make(PUBLIC_URL + "/setup", error="m")
        svg = qr.svg_inline(scale=10, border=2, dark="#1d1b2f", light="#fdf6ec")
        return {"mode": "welcome", "qr_svg": svg, "setup_url": PUBLIC_URL.split("://", 1)[-1] + "/setup"}
    now = today(conn)
    active = reminders.active(conn, now)
    shown = list(zip(active, reminders.monitor_sizes(active)))
    return {"mode": "home", "today": now, "upcoming": upcoming(conn, now, within_days=COMING_UP_DAYS, limit=4),
            "missing_count": len(missing_birthdays(conn)), "now": datetime.now(),
            "phone_url": PUBLIC_URL.split("://", 1)[-1], "reminders": shown,
            "more_reminders": len(active) - len(shown), "reminder_keys": " ".join(r.key for r in active),
            # With one reminder showing, "Next:" lists what comes after it.
            "next_up": [c for c in upcoming(conn, now, within_days=COMING_UP_DAYS)
                        if active and c.when > active[0].when][:3]}


@app.get("/screen")
def screen(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    return page(request, "screen.html", **_screen_context(conn))


@app.get("/screen/content")
def screen_content(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    return page(request, "_screen_content.html", **_screen_context(conn))
