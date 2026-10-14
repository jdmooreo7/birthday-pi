// Monitor behaviour: live clock, refresh from the Pi every 10 s, night dim while idle.
// URL params override timings for testing, e.g. /screen?idle=10&night=0-24
(function () {
  const params = new URLSearchParams(location.search);
  const IDLE_MS = (Number(params.get("idle")) || 5 * 60) * 1000;
  const [NIGHT_START, NIGHT_END] = (params.get("night") || "22-5").split("-").map(Number);
  const CURSOR_MS = 5000;
  const REFRESH_MS = 10 * 1000;
  let lastActive = Date.now();

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
    const date = document.getElementById("date");
    if (clock) clock.textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (date) date.textContent = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
    document.body.classList.toggle("idle-cursor", idle >= CURSOR_MS);
    document.body.classList.toggle("night", idle >= IDLE_MS && isNight(now));
  }

  async function refresh() {
    try {
      const res = await fetch("/screen/content", { cache: "no-store" });
      if (!res.ok) return;
      const html = await res.text();
      const content = document.getElementById("content");
      if (content.dataset.html !== html) {
        content.innerHTML = html;
        content.dataset.html = html;
        tick();
      }
    } catch (e) { /* keep showing the last known screen */ }
  }

  tick();
  setInterval(tick, 1000);
  setInterval(refresh, REFRESH_MS);
})();
