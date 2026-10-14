// On-screen PIN pad for the monitor (mouse now, touch later). Submits after 4 digits.
// Goes back to the main screen after 2 minutes without input.
(function () {
  const input = document.getElementById("pin");
  const dots = document.querySelectorAll(".dots span");
  const form = document.getElementById("pinform");
  let idle;
  function resetIdle() { clearTimeout(idle); idle = setTimeout(() => { location.href = "/screen"; }, 2 * 60 * 1000); }
  function show() { dots.forEach((d, i) => d.classList.toggle("on", i < input.value.length)); }
  document.querySelectorAll("[data-digit]").forEach(b => b.addEventListener("click", () => {
    if (input.value.length < 4) input.value += b.dataset.digit;
    show(); resetIdle();
    if (input.value.length === 4) form.submit();
  }));
  document.querySelector("[data-delete]").addEventListener("click", () => {
    input.value = input.value.slice(0, -1); show(); resetIdle();
  });
  ["mousemove", "touchstart"].forEach(e => window.addEventListener(e, resetIdle, { passive: true }));
  resetIdle();
})();
