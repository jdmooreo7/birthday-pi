"""Birthday Pi web app: the monitor screen (/screen) and the phone pages (everything else)."""
import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import date, datetime
from pathlib import Path

import segno
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from . import PRODUCT, db, devices, naming, photos, pins, reminders
from .dates import (MONTHS, SPECIAL_DATE_TYPES, how_far, missing_birthdays, remembering_today, short_date,
                    special_date_label, upcoming, valid_month_day)
from .reminders import possessive

HERE = Path(__file__).parent
COMING_UP_DAYS = 60  # "Coming up" lists only celebrations this many days ahead
PUBLIC_URL = os.environ.get("BIRTHDAY_PI_URL", "http://birthdaypi.local:8080").rstrip("/")

# The container's filesystem is read-only; uploads are buffered in TMPDIR on the data volume (see compose.yaml).
if os.environ.get("TMPDIR"):
    Path(os.environ["TMPDIR"]).mkdir(parents=True, exist_ok=True)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def static_url(name: str) -> str:
    """A /static link with a content hash, so browsers (and the kiosk) pick up new versions."""
    digest = hashlib.sha256((HERE / "static" / name).read_bytes()).hexdigest()[:10]
    return f"/static/{name}?v={digest}"


templates.env.globals.update(MONTHS=MONTHS, how_far=how_far, short_date=short_date, static_url=static_url,
                             product=PRODUCT)
templates.env.filters["possessive"] = possessive  # "Nana's", "James'"


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
            idle = idle_seconds(conn)
            context["test_idle"] = IDLE_CHOICES[idle] if idle != NORMAL_IDLE else None
            # Whoever it's for, by the name the family gave at setup (no "Grandma" default).
            owner = db.owner(conn)
            context.setdefault("owner_name", owner["name"] if owner else "")
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
    return page(request, "setup.html", owner_name="", errors={})


@app.post("/setup")
async def setup_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if db.is_set_up(conn):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    owner_name = str(form.get("owner_name", "")).strip()
    pin, pin2 = str(form.get("pin", "")), str(form.get("pin2", ""))
    errors = {}
    if not owner_name:
        errors["owner_name"] = "Please type the name the family uses."
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

def _who_people(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Who can be picked as using a phone: not someone the family is remembering."""
    return conn.execute("SELECT * FROM people WHERE remembered = 0 ORDER BY is_owner DESC, name").fetchall()


@app.get("/who")
def who_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    people = _who_people(conn)
    return page(request, "who.html", people=people, device=devices.current(conn, request), error=None)


@app.post("/who")
async def who_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    form = await request.form()
    new_name = str(form.get("new_name", "")).strip()
    if new_name:
        if len(new_name) > 40:
            people = _who_people(conn)
            return page(request, "who.html", 400, people=people, device=None, error="Please use 40 letters or fewer.")
        cur = conn.execute("INSERT INTO people (name) VALUES (?)", (new_name,))
        response = RedirectResponse(f"/people/{cur.lastrowid}?welcome=1", status_code=303)
        devices.remember(conn, request, response, cur.lastrowid, trusted_owner=False)
        return response
    try:
        person = conn.execute("SELECT * FROM people WHERE id = ?", (int(form.get("person_id", "")),)).fetchone()
    except ValueError:
        person = None
    if person is None or person["remembered"]:
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
        remembering=remembering_today(conn, now),
        upcoming=upcoming(conn, now, within_days=COMING_UP_DAYS), missing=missing_birthdays(conn),
        people_count=people_count, trusted_owner=devices.is_trusted_owner(device),
        pending=photos.pending_count(conn),
        to_name=len(naming.to_name(conn)) if devices.is_trusted_owner(device) else 0,
        to_check=len(naming.asking(conn)) if devices.is_trusted_owner(device) else 0,
        my_pending=conn.execute("SELECT COUNT(*) FROM photos WHERE status = 'pending' AND uploader_id = ?",
                                (device["person_id"],)).fetchone()[0],
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


# ---------- Testing: "pretend today is" and a shorter wait before photos ----------

def require_trusted_owner(conn: sqlite3.Connection, request: Request) -> sqlite3.Row:
    device = require_device(conn, request)
    if not devices.is_trusted_owner(device):
        raise RedirectTo("/pin")
    return device


# How long the monitor waits without input before photos start. Normal is 5 minutes;
# shorter waits are for testing and show the testing banner.
IDLE_CHOICES = {10: "10 seconds", 30: "30 seconds", 60: "1 minute", 300: "5 minutes (normal)"}
NORMAL_IDLE = 300


def idle_seconds(conn: sqlite3.Connection) -> int:
    value = int(db.get_setting(conn, "test_idle_seconds", str(NORMAL_IDLE)))
    return value if value in IDLE_CHOICES else NORMAL_IDLE


def _testing_page(request, conn, device, status_code=200, error=None):
    return page(request, "pretend_date.html", status_code, device=device, real=date.today(), current=today(conn),
                error=error, idle=idle_seconds(conn), IDLE_CHOICES=IDLE_CHOICES)


# ---------- Screen at night (Grandma's choice) and Help ----------

# How dark the monitor goes at night: (what Grandma sees, opacity of the black layer, a line about it)
NIGHT_LEVELS = {
    "little": ("A little", 0.5, "You can still see the clock clearly."),
    "mostly": ("Mostly", 0.85, "The clock is faint."),
    "full": ("Fully dark", 1.0, "A black screen. The monitor's own light stays on."),
}


def hour_label(h: int) -> str:
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


templates.env.globals["hour_label"] = hour_label


def night(conn: sqlite3.Connection) -> dict:
    """Grandma's night settings: dim or not, from and until which hour, and how dark. Default 10 pm to 5 am."""
    def hour(key, default):
        value = db.get_setting(conn, key, str(default))
        return int(value) if value.isdigit() and int(value) < 24 else default
    level = db.get_setting(conn, "night_level", "mostly")
    return {"on": db.get_setting(conn, "night_on", "1") == "1", "start": hour("night_from", 22),
            "end": hour("night_until", 5), "level": level if level in NIGHT_LEVELS else "mostly"}


def night_for_screen(conn: sqlite3.Connection) -> str:
    n = night(conn)
    return f"{n['start']}-{n['end']}-{NIGHT_LEVELS[n['level']][1]}" if n["on"] else "off"


@app.get("/settings/night")
def night_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return page(request, "night.html", device=device, night=night(conn), LEVELS=NIGHT_LEVELS,
                trusted_owner=devices.is_trusted_owner(device), owner=db.owner(conn),
                saved=request.query_params.get("saved") == "1")


@app.post("/settings/night")
async def night_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    form = await request.form()
    current = night(conn)
    try:
        start, end = int(str(form.get("start"))), int(str(form.get("end")))
    except ValueError:
        start, end = current["start"], current["end"]
    level = str(form.get("level", current["level"]))
    db.set_setting(conn, "night_on", "0" if form.get("on") == "0" else "1")
    if 0 <= start < 24 and 0 <= end < 24 and start != end:
        db.set_setting(conn, "night_from", str(start))
        db.set_setting(conn, "night_until", str(end))
    if level in NIGHT_LEVELS:
        db.set_setting(conn, "night_level", level)
    return RedirectResponse("/settings/night?saved=1", status_code=303)


def helper(conn: sqlite3.Connection) -> dict | None:
    """Who Grandma calls when she's stuck, if the family has filled it in."""
    name, phone = db.get_setting(conn, "helper_name", ""), db.get_setting(conn, "helper_phone", "")
    return {"name": name, "phone": phone, "tel": re.sub(r"[^0-9+]", "", phone)} if name and phone else None


@app.get("/help")
def help_page(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = devices.current(conn, request)
    return page(request, "help.html", device=device, night=night(conn), helper=helper(conn),
                trusted_owner=devices.is_trusted_owner(device))


@app.get("/settings/helper")
def helper_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    return page(request, "helper.html", device=device, helper=helper(conn) or {"name": "", "phone": ""})


@app.post("/settings/helper")
async def helper_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    form = await request.form()
    name, phone = str(form.get("name", "")).strip()[:60], str(form.get("phone", "")).strip()[:30]
    if name and re.search(r"[0-9]", phone):
        db.set_setting(conn, "helper_name", name)
        db.set_setting(conn, "helper_phone", phone)
    else:
        conn.execute("DELETE FROM settings WHERE key IN ('helper_name', 'helper_phone')")
    return RedirectResponse("/help", status_code=303)


@app.get("/settings/date")
def pretend_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    return _testing_page(request, conn, device)


@app.post("/settings/date")
async def pretend_save(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    form = await request.form()
    if form.get("action") == "normal":
        conn.execute("DELETE FROM settings WHERE key IN ('pretend_date', 'test_idle_seconds')")
        return RedirectResponse("/", status_code=303)
    try:
        chosen = date.fromisoformat(str(form.get("date", "")))
        idle = int(str(form.get("idle", NORMAL_IDLE)))
    except ValueError:
        return _testing_page(request, conn, device, 400, error="Please pick a date.")
    if chosen == date.today():
        conn.execute("DELETE FROM settings WHERE key = 'pretend_date'")
    else:
        db.set_setting(conn, "pretend_date", chosen.isoformat())
    if idle in IDLE_CHOICES and idle != NORMAL_IDLE:
        db.set_setting(conn, "test_idle_seconds", str(idle))
    else:
        conn.execute("DELETE FROM settings WHERE key = 'test_idle_seconds'")
    return RedirectResponse("/", status_code=303)


def _people_list(conn: sqlite3.Connection) -> list[dict]:
    dates: dict[int, list[str]] = {}
    for a in conn.execute("SELECT * FROM anniversaries ORDER BY month, day"):
        label = special_date_label(a["kind"], a["label"])
        dates.setdefault(a["person_id"], []).append(f"{label} · {MONTHS[a['month'] - 1]} {a['day']}")
    result = []
    for p in conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name"):
        birthday = f"{MONTHS[p['birth_month'] - 1]} {p['birth_day']}" if p["birth_month"] else None
        result.append({"id": p["id"], "name": p["name"], "is_owner": p["is_owner"], "remembered": p["remembered"],
                       "birthday": birthday, "special_dates": dates.get(p["id"], [])})
    return result


@app.get("/people")
def people_list(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return page(request, "people.html", device=device, people=_people_list(conn))


def _s(v) -> str:
    return "" if v is None else str(v)


def _form_values(conn: sqlite3.Connection, person: sqlite3.Row | None) -> dict:
    """Values for the person form. Special date rows are ann_<i>_kind/_label/_month/_day/_year,
    one per saved date plus one blank row for adding another."""
    values = {"name": "", "birth_month": "", "birth_day": "", "birth_year": "",
              "remembered": "1" if person is not None and person["remembered"] else ""}
    anns = []
    if person is not None:
        values.update(name=person["name"], birth_month=_s(person["birth_month"]),
                      birth_day=_s(person["birth_day"]), birth_year=_s(person["birth_year"]))
        anns = conn.execute("SELECT * FROM anniversaries WHERE person_id = ? ORDER BY id", (person["id"],)).fetchall()
    for i, a in enumerate(anns):
        values.update({f"ann_{i}_kind": a["kind"], f"ann_{i}_label": _s(a["label"]), f"ann_{i}_month": _s(a["month"]),
                       f"ann_{i}_day": _s(a["day"]), f"ann_{i}_year": _s(a["year"])})
    i = len(anns)
    values.update({f"ann_{i}_kind": next(iter(SPECIAL_DATE_TYPES)), f"ann_{i}_label": "", f"ann_{i}_month": "",
                   f"ann_{i}_day": "", f"ann_{i}_year": ""})
    values["ann_count"] = i + 1
    return values


MAX_ANNIVERSARY_ROWS = 20
FUTURE_YEARS = 10  # special dates may be dated up to this many years ahead


def _parse_person_form(form) -> tuple[dict, dict, dict]:
    """Returns (values to redisplay, cleaned data, errors)."""
    try:
        count = min(max(int(form.get("ann_count", "0")), 0), MAX_ANNIVERSARY_ROWS)
    except ValueError:
        count = 0
    keys = ["name", "birth_month", "birth_day", "birth_year", "remembered"]
    for i in range(count):
        keys += [f"ann_{i}_kind", f"ann_{i}_label", f"ann_{i}_month", f"ann_{i}_day", f"ann_{i}_year", f"ann_{i}_remove"]
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

    clean: dict = {"name": values["name"], "anniversaries": [], "remembered": bool(values["remembered"])}
    if not values["name"]:
        errors["name"] = "Please type a name."
    elif len(values["name"]) > 40:
        errors["name"] = "Please use 40 letters or fewer."
    clean["birth_month"], clean["birth_day"], clean["birth_year"] = date_parts("birth", this_year)

    for i in range(count):
        prefix = f"ann_{i}"
        if values[f"{prefix}_remove"]:
            continue
        month, day, year = date_parts(prefix, this_year + FUTURE_YEARS)  # e.g. a graduation next year
        if month is None and day is None and year is None:
            continue  # a blank row, or one cleared to remove it
        kind, label = values[f"{prefix}_kind"], values[f"{prefix}_label"]
        if kind not in SPECIAL_DATE_TYPES:
            errors[f"{prefix}_kind"] = "Please pick what it is."
        if kind == "other" and not label:
            errors[f"{prefix}_label"] = "Please type what you call it."
        elif kind == "other" and len(label) > 40:
            errors[f"{prefix}_label"] = "Please use 40 letters or fewer."
        clean["anniversaries"].append((kind, month, day, year, label if kind == "other" else None))
    values["ann_count"] = count
    return values, clean, errors


def _save_person(conn: sqlite3.Connection, person_id: int | None, c: dict, can_remember: bool = False) -> int:
    """can_remember: the person it's for, on a trusted phone, may mark someone as remembered."""
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
    if can_remember:
        conn.execute("UPDATE people SET remembered = ? WHERE id = ? AND is_owner = 0", (int(c["remembered"]), person_id))
    conn.execute("DELETE FROM anniversaries WHERE person_id = ?", (person_id,))
    conn.executemany(
        "INSERT INTO anniversaries (person_id, kind, month, day, year, label) VALUES (?, ?, ?, ?, ?, ?)",
        [(person_id, *a) for a in c["anniversaries"]],
    )
    return person_id


def _person_page(request, conn, device, person, values, errors, status_code=200, welcome=False):
    # Grandma can check the faces named as this person ("Is this all Leo?").
    face_photos = naming.photo_count(conn, person["id"]) if person and devices.is_trusted_owner(device) \
        and naming.person_faces(conn, person["id"]) else 0
    return page(request, "person_form.html", status_code, device=device, person=person, values=values,
                errors=errors, welcome=welcome, this_year=today().year, SPECIAL_DATE_TYPES=SPECIAL_DATE_TYPES,
                can_remember=devices.is_trusted_owner(device) and not (person and person["is_owner"]),
                face_photos=face_photos)


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
    _save_person(conn, None, clean, can_remember=devices.is_trusted_owner(device))
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
    _save_person(conn, person_id, clean, can_remember=devices.is_trusted_owner(device))
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
        # Their face data goes too: a removed person is forgotten, not left waiting to be named again.
        for face_id in naming.forget_person(conn, person_id):
            photos.face_crop_path(face_id).unlink(missing_ok=True)
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
    return RedirectResponse("/people", status_code=303)




# ---------- Photos (phone) ----------

@app.get("/photos")
def photo_list(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    trusted = devices.is_trusted_owner(device)
    if trusted:
        sections = [
            ("Waiting for your OK", photos.listing(conn, "status = 'pending'")),
            ("On the screen", photos.listing(conn, "status = 'approved' AND hidden = 0")),
            ("Hidden", photos.listing(conn, "status = 'approved' AND hidden = 1")),
        ]
    else:
        sections = [
            (f"Your photos waiting for {db.owner(conn)['name']}", photos.listing(conn, "status = 'pending' AND uploader_id = ?",
                                                               (device["person_id"],))),
            ("On the screen", photos.listing(conn, "status = 'approved' AND hidden = 0")),
        ]
    return page(request, "photos.html", device=device, sections=sections, trusted_owner=trusted,
                pending=photos.pending_count(conn), deleted=request.query_params.get("deleted") == "1")


@app.get("/photos/add")
def photo_add_form(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    return page(request, "photo_add.html", device=device, trusted_owner=devices.is_trusted_owner(device))


UPLOAD_LOCK = threading.Lock()  # one photo resized at a time keeps memory under the 256 MB limit


def _save_photo(conn: sqlite3.Connection, data: bytes, person_id: int, approved: bool) -> str | None:
    with UPLOAD_LOCK:
        return photos.save_upload(conn, data, person_id, approved)


@app.post("/photos/add")
async def photo_add(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    trusted = devices.is_trusted_owner(device)
    form = await request.form(max_files=photos.MAX_FILES_PER_UPLOAD)
    added, duplicates, problems = [], 0, []
    for upload in form.getlist("photos"):
        if not hasattr(upload, "read"):
            continue
        data = await upload.read()
        if not data:
            continue
        try:
            # Off the event loop, so the monitor and the health check keep answering during a big upload.
            photo_id = await run_in_threadpool(_save_photo, conn, data, device["person_id"], trusted)
        except photos.UploadError as e:
            problems.append(f"{upload.filename or 'A photo'} {e}.")
            continue
        if photo_id:
            added.append(photo_id)
        else:
            duplicates += 1
    return page(request, "photo_added.html", device=device, trusted_owner=trusted,
                added=[photos.get(conn, i) for i in added], duplicates=duplicates, problems=problems)


@app.get("/photos/review")
def photo_review(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    return page(request, "photo_review.html", device=device, waiting=photos.listing(conn, "status = 'pending'"))


def _get_photo(conn: sqlite3.Connection, photo_id: str) -> sqlite3.Row:
    photo = photos.get(conn, photo_id)
    if photo is None:
        raise RedirectTo("/photos")
    return photo


@app.get("/photos/{photo_id}")
def photo_detail(photo_id: str, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_device(conn, request)
    photo = _get_photo(conn, photo_id)
    people = conn.execute("SELECT id, name FROM people ORDER BY is_owner DESC, name").fetchall()
    return page(request, "photo_detail.html", device=device, photo=photo, people=people,
                tagged=photos.tags(conn, photo_id), trusted_owner=devices.is_trusted_owner(device),
                recognised=photos.face_names(conn, photo_id),
                saved=request.query_params.get("saved") == "1")


@app.post("/photos/{photo_id}/tags")
async def photo_tags(photo_id: str, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_device(conn, request)
    _get_photo(conn, photo_id)
    form = await request.form()
    ids = set()
    for v in form.getlist("person"):
        try:
            ids.add(int(v))
        except ValueError:
            pass
    photos.set_tags(conn, photo_id, ids)
    return RedirectResponse(f"/photos/{photo_id}?saved=1", status_code=303)


def _decide(conn: sqlite3.Connection, photo_id: str, action: str) -> None:
    photo = photos.get(conn, photo_id)
    if photo is None:
        return
    if action == "approve" and photo["status"] == "pending":
        conn.execute("UPDATE photos SET status = 'approved' WHERE id = ?", (photo_id,))
    elif action == "reject" and photo["status"] == "pending":
        photos.delete(conn, photo_id)  # "No" means it never goes on the screen; the file is removed
    elif action == "hide":
        conn.execute("UPDATE photos SET hidden = 1 WHERE id = ?", (photo_id,))
    elif action == "show":
        conn.execute("UPDATE photos SET hidden = 0 WHERE id = ?", (photo_id,))


@app.post("/photos/{photo_id}/decision")
async def photo_decision(photo_id: str, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    form = await request.form()
    _decide(conn, photo_id, str(form.get("action", "")))
    back = str(form.get("back", ""))
    return RedirectResponse(back if back in ("/photos/review", "/photos") else "/photos", status_code=303)


@app.get("/photos/{photo_id}/delete")
def photo_delete_confirm(photo_id: str, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    return page(request, "photo_delete.html", device=device, photo=_get_photo(conn, photo_id))


@app.post("/photos/{photo_id}/delete")
def photo_delete(photo_id: str, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """Grandma only. The photo, its thumbnail and any faces found in it (crops and face data) go."""
    require_trusted_owner(conn, request)
    if photos.get(conn, photo_id):
        photos.delete(conn, photo_id)
    return RedirectResponse("/photos?deleted=1", status_code=303)


@app.get("/photo-files/{name}")
def photo_file(name: str):
    """Photo ids are random, so only someone shown the page knows a photo's address."""
    m = re.fullmatch(r"([0-9a-f]{16})(-thumb)?\.jpg", name)
    path = photos.file_path(m.group(1), bool(m.group(2))) if m else None
    if path is None or not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------- Naming faces (M6): Grandma only; the faces worker fills the tables ----------

FACE_WORKER_LATE = 60  # seconds without a heartbeat before the page says the worker isn't running
TO_NAME_SHOWN = 4  # groups listed before "Show more"


def _get_group(conn: sqlite3.Connection, group_id: int) -> sqlite3.Row:
    g = naming.group(conn, group_id)
    if g is None:
        raise RedirectTo("/faces")
    return g


@app.get("/faces")
def faces_list(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """Who's in your photos? Groups still to name, biggest first, then the people already named."""
    device = require_trusted_owner(conn, request)
    todo = naming.to_name(conn)
    show_all = request.query_params.get("all") == "1"
    shown = todo if show_all else todo[:TO_NAME_SHOWN]
    strips = {g["id"]: naming.face_ids(conn, g["id"], limit=3) for g in shown}
    named = naming.named_people(conn)
    named_groups = conn.execute(
        "SELECT COUNT(*) FROM (SELECT g.id FROM face_groups g JOIN faces f ON f.group_id = g.id "
        "JOIN photos ph ON ph.id = f.photo_id AND ph.status = 'approved' WHERE g.person_id IS NOT NULL "
        "GROUP BY g.id HAVING COUNT(DISTINCT f.photo_id) >= ?)", (naming.OFFERED_AT,)).fetchone()[0]
    counts = conn.execute(
        "SELECT COUNT(*) AS photos, COALESCE(SUM(faces_scanned), 0) AS scanned FROM photos").fetchone()
    beat = db.get_setting(conn, "faces_heartbeat")
    running = bool(beat) and (datetime.now() - datetime.fromisoformat(beat)).total_seconds() < FACE_WORKER_LATE
    return page(request, "faces.html", device=device, todo=todo, shown=shown, strips=strips, named=named,
                named_groups=named_groups, counts=counts, running=running, offered_at=naming.OFFERED_AT,
                set_aside=len(naming.set_aside(conn)), undo=_undo_strip(conn, request))


def _undo_strip(conn: sqlite3.Connection, request: Request) -> dict | None:
    """The "Set aside: not family. Undo" strip, on the page she lands on straight after setting a group aside.
    It goes with her next tap, since that loads a page without ?set_aside."""
    g = naming.group(conn, _int_param(request, "set_aside"))
    if g is None or g["ignored"] not in naming.IGNORE_REASONS:
        return None
    return {"group": g, "label": naming.IGNORE_REASONS[g["ignored"]], "faces": naming.face_ids(conn, g["id"], limit=1)}


# Set aside: groups she said aren't family or aren't people, to name after all. Declared before
# /faces/{group_id} so "set-aside" isn't read as a group id.
@app.get("/faces/set-aside")
def faces_set_aside(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    groups = naming.set_aside(conn)
    strips = {g["id"]: naming.face_ids(conn, g["id"], limit=3) for g in groups}
    return page(request, "face_set_aside.html", device=device, groups=groups, strips=strips,
                labels=naming.IGNORE_REASONS)


# "Is this Leo?" (M7): faces in new photos the faces worker wasn't sure about. Declared before
# /faces/{group_id} so "ask" isn't read as a group id.
@app.get("/faces/ask")
def face_ask(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    after, yes = (_int_param(request, k) for k in ("after", "yes"))
    waiting = naming.asking(conn)
    later = [a for a in waiting if a["id"] > after]
    if not later:
        return page(request, "face_ask.html", device=device, q=None, yes=yes, skipped=len(waiting))
    q = later[0]
    face = conn.execute("SELECT f.photo_id, f.x, f.y, f.w, f.h, ph.width, ph.height, p.name AS uploader "
                        "FROM faces f JOIN photos ph ON ph.id = f.photo_id LEFT JOIN people p ON p.id = ph.uploader_id "
                        "WHERE f.id = ?", (q["id"],)).fetchone()
    ring = None
    if face["width"] and face["height"]:
        ring = {k: round(100 * v / face[d], 1) for k, v, d in (
            ("left", face["x"], "width"), ("top", face["y"], "height"), ("w", face["w"], "width"), ("h", face["h"], "height"))}
    return page(request, "face_ask.html", device=device, q=q, face=face, ring=ring, yes=yes, left=len(later))


@app.post("/faces/ask/{face_id}")
async def face_ask_save(face_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    form = await request.form()
    action = str(form.get("action", ""))
    yes = _int_param(request, "yes")
    if naming.ask(conn, face_id) and action in ("yes", "no"):
        naming.answer(conn, face_id, yes=action == "yes")
        yes += action == "yes"
    return RedirectResponse(f"/faces/ask?after={face_id}&yes={yes}", status_code=303)


def _int_param(request: Request, key: str) -> int:
    try:
        return max(0, int(request.query_params.get(key, 0)))
    except ValueError:
        return 0


@app.get("/faces/{group_id}")
def face_group(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """All the same person? Every face in the group; Grandma ticks the ones that aren't them."""
    device = require_trusted_owner(conn, request)
    g = _get_group(conn, group_id)
    todo = [t["id"] for t in naming.to_name(conn)]
    return page(request, "face_group.html", device=device, group=g, faces=naming.face_ids(conn, group_id),
                position=(todo.index(group_id) + 1) if group_id in todo else None, total=len(todo),
                skip_to=naming.next_after(conn, group_id), undo=_undo_strip(conn, request))


@app.post("/faces/{group_id}")
async def face_group_save(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """Takes out the ticked faces, then goes on to "Who is this?", or sets the group aside."""
    require_trusted_owner(conn, request)
    _get_group(conn, group_id)
    form = await request.form()
    out = []
    for v in form.getlist("out"):
        try:
            out.append(int(v))
        except ValueError:
            pass
    naming.take_out(conn, group_id, out)
    action = str(form.get("action", ""))
    if action in naming.IGNORE_REASONS:
        naming.ignore(conn, group_id, action)
        after = naming.next_after(conn, group_id)
        return RedirectResponse(f"/faces/{after}?set_aside={group_id}" if after else f"/faces?set_aside={group_id}",
                                status_code=303)
    return RedirectResponse(f"/faces/{group_id}/who", status_code=303)


@app.get("/faces/{group_id}/who")
def face_who(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    g = _get_group(conn, group_id)
    people = conn.execute("SELECT * FROM people ORDER BY is_owner DESC, name").fetchall()
    details = {}
    for p in people:
        bday = f"Birthday {MONTHS[p['birth_month'] - 1][:3]} {p['birth_day']}" if p["birth_month"] else "No birthday yet"
        n = naming.photo_count(conn, p["id"])
        details[p["id"]] = f"{bday} · " + (f"in {n} photo{'s' if n != 1 else ''}" if n else "no photos yet")
    return page(request, "face_who.html", device=device, group=g, strip=naming.face_ids(conn, group_id, limit=3),
                people=people, details=details, error=None)


@app.post("/faces/{group_id}/who")
async def face_who_save(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    _get_group(conn, group_id)
    form = await request.form()
    person_id = None
    try:
        person_id = int(form.get("person_id", ""))
    except ValueError:
        typed = str(form.get("new_name", "")).strip()
        if typed and len(typed) <= 40:
            person_id = naming.find_or_add_person(conn, typed)
    if person_id is None or not conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone():
        return RedirectResponse(f"/faces/{group_id}/who", status_code=303)
    naming.name(conn, group_id, person_id)
    return RedirectResponse(f"/faces/{group_id}/named", status_code=303)


@app.get("/faces/{group_id}/named")
def face_named(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """That's Mia: how many photos she's in now, and where to go next."""
    device = require_trusted_owner(conn, request)
    g = _get_group(conn, group_id)
    if g["person_id"] is None:
        return RedirectResponse(f"/faces/{group_id}", status_code=303)
    person = conn.execute("SELECT * FROM people WHERE id = ?", (g["person_id"],)).fetchone()
    birthday = f"{MONTHS[person['birth_month'] - 1]} {person['birth_day']}" if person["birth_month"] else None
    return page(request, "face_named.html", device=device, group=g, person=person, birthday=birthday,
                total=naming.photo_count(conn, person["id"]),
                before=naming.photo_count(conn, person["id"], except_group=group_id),
                left=len(naming.to_name(conn)), next_group=naming.next_after(conn, None))


@app.post("/faces/{group_id}/undo")
def face_undo(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    _get_group(conn, group_id)
    naming.unname(conn, group_id)
    return RedirectResponse(f"/faces/{group_id}/who", status_code=303)


@app.post("/faces/{group_id}/unignore")
async def face_unignore(group_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """Undo goes back to the group as it was; "Name them after all" goes on to "Who is this?"."""
    require_trusted_owner(conn, request)
    _get_group(conn, group_id)
    form = await request.form()
    naming.unignore(conn, group_id)
    then = "/who" if form.get("then") == "who" else ""
    return RedirectResponse(f"/faces/{group_id}{then}", status_code=303)


# "Is this all Leo?" (M7): every face named as someone, to take out the ones that aren't them.
@app.get("/people/{person_id}/faces")
def person_faces(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    device = require_trusted_owner(conn, request)
    person = _get_person(conn, person_id)
    shown = naming.person_faces(conn, person_id)
    if not shown:
        return RedirectResponse(f"/people/{person_id}", status_code=303)
    return page(request, "face_person.html", device=device, person=person, faces=shown,
                photos=naming.photo_count(conn, person_id))


@app.post("/people/{person_id}/faces")
async def person_faces_save(person_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_trusted_owner(conn, request)
    _get_person(conn, person_id)
    form = await request.form()
    out = []
    for v in form.getlist("out"):
        try:
            out.append(int(v))
        except ValueError:
            pass
    naming.not_person(conn, person_id, out)
    return RedirectResponse(f"/people/{person_id}", status_code=303)


@app.get("/face-files/{face_id}.jpg")
def face_file(face_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """Face data is Grandma's to see: only her trusted devices get the crops (face ids are guessable)."""
    require_trusted_owner(conn, request)
    path = photos.face_crop_path(face_id)
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------- Monitor: Grandma approves photos with her PIN ----------

SCREEN_COOKIE = "bp_screen"
SCREEN_UNLOCK_SECONDS = 10 * 60


def _screen_unlocked(conn: sqlite3.Connection, request: Request) -> bool:
    token = request.cookies.get(SCREEN_COOKIE)
    stored = db.get_setting(conn, "screen_unlock")
    if not token or not stored:
        return False
    digest, until = stored.split("|")
    return hashlib.sha256(token.encode()).hexdigest() == digest and time.time() < float(until)


@app.get("/screen/approve")
def screen_approve(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    waiting = photos.listing(conn, "status = 'pending'")
    if not waiting:
        return RedirectResponse("/screen", status_code=303)
    if not _screen_unlocked(conn, request):
        return page(request, "screen_pin.html", owner=db.owner(conn), waiting=waiting, error=None,
                    locked=pins.seconds_locked(conn))
    return page(request, "screen_approve.html", waiting=waiting)


@app.post("/screen/approve/pin")
async def screen_approve_pin(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    require_setup(conn)
    form = await request.form()
    if pins.check_pin(conn, str(form.get("pin", ""))) == "ok":
        token = secrets.token_urlsafe(32)
        db.set_setting(conn, "screen_unlock",
                       f"{hashlib.sha256(token.encode()).hexdigest()}|{time.time() + SCREEN_UNLOCK_SECONDS}")
        response = RedirectResponse("/screen/approve", status_code=303)
        response.set_cookie(SCREEN_COOKIE, token, max_age=SCREEN_UNLOCK_SECONDS, httponly=True, samesite="lax")
        return response
    locked = pins.seconds_locked(conn)
    return page(request, "screen_pin.html", 400, owner=db.owner(conn), waiting=photos.listing(conn, "status = 'pending'"),
                error=None if locked else "That PIN isn't right. Please try again.", locked=locked)


@app.post("/screen/approve/decide")
async def screen_approve_decide(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    if _screen_unlocked(conn, request):
        form = await request.form()
        if form.get("action") in ("approve", "reject"):
            _decide(conn, str(form.get("photo_id", "")), str(form.get("action")))
    return RedirectResponse("/screen/approve", status_code=303)


@app.post("/screen/approve/done")
def screen_approve_done(conn: sqlite3.Connection = Depends(get_conn)):
    conn.execute("DELETE FROM settings WHERE key = 'screen_unlock'")
    response = RedirectResponse("/screen", status_code=303)
    response.delete_cookie(SCREEN_COOKIE)
    return response


@app.get("/screen/photos")
def screen_photos(conn: sqlite3.Connection = Depends(get_conn)) -> JSONResponse:
    if not db.is_set_up(conn):
        return JSONResponse({"photos": [], "title": ""})
    return JSONResponse(photos.slideshow(conn, today(conn)))


# ---------- Monitor ----------

def _screen_context(conn: sqlite3.Connection) -> dict:
    if not db.is_set_up(conn):
        qr = segno.make(PUBLIC_URL + "/setup", error="m")
        svg = qr.svg_inline(scale=10, border=2, dark="#1d1b2f", light="#fdf6ec")
        return {"mode": "welcome", "qr_svg": svg, "setup_url": PUBLIC_URL.split("://", 1)[-1] + "/setup"}
    now = today(conn)
    active = reminders.active(conn, now)
    shown = list(zip(active, reminders.monitor_sizes(active)))
    remembering = remembering_today(conn, now)
    return {"mode": "home", "today": now, "remembering": remembering,
            # A quiet card for someone remembered today takes the room of two "Coming up" rows.
            "upcoming": upcoming(conn, now, within_days=COMING_UP_DAYS, limit=2 if remembering else 4),
            "missing_count": len(missing_birthdays(conn)), "now": datetime.now(), "pending": photos.pending_count(conn),
            "phone_url": PUBLIC_URL.split("://", 1)[-1], "reminders": shown,
            "more_reminders": len(active) - len(shown), "reminder_keys": " ".join(r.key for r in active),
            # With one reminder showing, "Next:" lists what comes after it.
            "next_up": [c for c in upcoming(conn, now, within_days=COMING_UP_DAYS)
                        if active and c.when > active[0].when][:3]}


def _screen_build() -> str:
    """Changes whenever the monitor's script or styles change; the open screen reloads itself."""
    return static_url("screen.js") + static_url("screen.css")


@app.get("/screen")
def screen(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    return page(request, "screen.html", build=_screen_build(), idle=idle_seconds(conn), night=night_for_screen(conn),
                **_screen_context(conn))


@app.get("/screen/content")
def screen_content(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    response = page(request, "_screen_content.html", **_screen_context(conn))
    response.headers["X-Screen-Build"] = _screen_build()
    response.headers["X-Screen-Idle"] = str(idle_seconds(conn))
    response.headers["X-Screen-Night"] = night_for_screen(conn)
    return response
