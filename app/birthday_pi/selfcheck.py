"""Container health checks that heal themselves.

Docker marks a container unhealthy but doesn't restart it. So after several failed checks in a row,
this stops the container's main process and Docker's restart policy brings the container back.
With `init: true` in compose.yaml the main process isn't PID 1, so it can be stopped from inside
the container without any extra permissions. Docker runs it: python -m birthday_pi.selfcheck app|faces
"""
import os
import signal
import sys
import time
import urllib.request

ATTEMPTS = 3
GAP_SECONDS = 5


def app_ok() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=5)
        return True
    except OSError:
        return False


def faces_ok() -> bool:
    from .faces import healthy  # only in the faces container, which has NumPy
    return healthy()


# Which check to run, and a piece of the main process's command line to find it by.
CHECKS = {"app": (app_ok, "uvicorn"), "faces": (faces_ok, "birthday_pi.faces")}


def main_pids(marker: str) -> list[int]:
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in (1, os.getpid()):
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if marker in cmd and "selfcheck" not in cmd:
            pids.append(int(entry))
    return pids


def say(message: str) -> None:
    """Into the container's own log (what Dozzle shows), not just Docker's health record."""
    print(message, flush=True)
    try:
        with open("/proc/1/fd/1", "w") as out:
            out.write(f"selfcheck: {message}\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    name = (sys.argv[1:] if argv is None else argv)[0]
    ok, marker = CHECKS[name]
    for attempt in range(ATTEMPTS):
        if ok():
            return 0
        if attempt < ATTEMPTS - 1:
            time.sleep(GAP_SECONDS)
    for pid in main_pids(marker):
        say(f"{name} failed {ATTEMPTS} health checks in a row; stopping it so Docker restarts the container")
        os.kill(pid, signal.SIGKILL)
    return 1


if __name__ == "__main__":
    sys.exit(main())
