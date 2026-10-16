// Monitor behaviour: live clock, refresh from the Pi every 10 s, night dim while idle,
// and a new reminder wakes the screen. The date comes from the Pi (it may be a pretend date).
// URL params override timings for testing, e.g. /screen?idle=10&night=0-24
(function () {
  const params = new URLSearchParams(location.search);
  // Wait before photos and night dim: ?idle= for a quick test, else the Pi's setting (5 minutes unless testing).
  let IDLE_MS = (Number(params.get("idle")) || Number(document.body.dataset.idle) || 5 * 60) * 1000;
  // Night hours and how dark: Grandma's choice from the Pi ("22-5-0.85" or "off"), unless ?night= is given.
  let [NIGHT_START, NIGHT_END] = (params.get("night") || "22-5").split("-").map(Number);
  let NIGHT_ON = true;
  function setNight(value) {
    if (params.get("night") || !value) return;
    NIGHT_ON = value !== "off";
    if (!NIGHT_ON) return;
    const [start, end, dim] = value.split("-");
    NIGHT_START = Number(start); NIGHT_END = Number(end);
    document.body.style.setProperty("--night-dim", dim);
  }
  setNight(document.body.dataset.night);
  const CURSOR_MS = 5000;
  const REFRESH_MS = 10 * 1000;
  const PHOTO_MS = (Number(params.get("photo")) || 60) * 1000;  // each photo stays up 1 minute
  let lastActive = Date.now();
  let photoList = [], photoIdx = -1, photoTimer = null, front = 0, celebrating = "";

  function wake() { lastActive = Date.now(); tick(); }
  ["mousemove", "mousedown", "touchstart", "keydown", "wheel"].forEach(e =>
    window.addEventListener(e, wake, { passive: true }));

  function isNight(d) {
    const h = d.getHours();
    return NIGHT_START > NIGHT_END ? (h >= NIGHT_START || h < NIGHT_END) : (h >= NIGHT_START && h < NIGHT_END);
  }

  function tick() {
    const now = new Date();
    const idle = Date.now() - lastActive;
    const clock = document.getElementById("clock");
    if (clock) clock.textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    document.body.classList.toggle("idle-cursor", idle >= CURSOR_MS);
    document.body.classList.toggle("night", NIGHT_ON && idle >= IDLE_MS && isNight(now));
    const photoClock = document.getElementById("photo-clock");
    if (photoClock) photoClock.textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    const cl = document.body.classList;
    const showPhotos = idle >= IDLE_MS && photoList.length > 0;
    if (showPhotos && !cl.contains("photos")) { cl.add("photos"); nextPhoto(); photoTimer = setInterval(nextPhoto, PHOTO_MS); }
    if (!showPhotos && cl.contains("photos")) { cl.remove("photos"); clearInterval(photoTimer); }
  }

  // Slideshow: approved photos, or only the celebrated person's photos on their day.
  function nextPhoto() {
    if (!photoList.length) return;
    photoIdx = (photoIdx + 1) % photoList.length;
    const imgs = document.querySelectorAll("#photos img");
    const next = imgs[1 - front];
    next.onload = () => { next.classList.add("show"); imgs[front].classList.remove("show"); front = 1 - front; };
    next.src = photoList[photoIdx];
  }

  async function loadPhotos() {
    try {
      const data = await (await fetch("/screen/photos", { cache: "no-store" })).json();
      const changed = [...data.photos].sort().join() !== [...photoList].sort().join() || data.title !== celebrating;
      if (!changed) return;
      celebrating = data.title;
      photoList = data.photos.sort(() => Math.random() - 0.5);
      photoIdx = -1;
      const title = document.getElementById("photo-title");
      title.textContent = celebrating;
    } catch (e) { /* keep the current photos */ }
  }

  function reminderKeys() {
    const el = document.querySelector("[data-reminders]");
    return new Set(el && el.dataset.reminders ? el.dataset.reminders.split(" ") : []);
  }
  let seenReminders = reminderKeys();

  async function refresh() {
    try {
      const res = await fetch("/screen/content", { cache: "no-store" });
      if (!res.ok) return;
      const build = res.headers.get("X-Screen-Build");
      if (build && build !== document.body.dataset.build) { location.reload(); return; }  // app was updated
      const idle = Number(res.headers.get("X-Screen-Idle"));
      if (idle && !params.get("idle")) IDLE_MS = idle * 1000;
      setNight(res.headers.get("X-Screen-Night"));
      const html = await res.text();
      const content = document.getElementById("content");
      if (content.dataset.html !== html) {
        content.innerHTML = html;
        content.dataset.html = html;
        const keys = reminderKeys();
        const isNew = [...keys].some(k => !seenReminders.has(k));
        seenReminders = keys;
        if (isNew) wake(); else tick();
      }
    } catch (e) { /* keep showing the last known screen */ }
  }

  tick();
  setInterval(tick, 1000);
  setInterval(refresh, REFRESH_MS);
  loadPhotos();
  setInterval(loadPhotos, 60 * 1000);
})();
