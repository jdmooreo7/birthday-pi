import signal

from birthday_pi import selfcheck


def _run(monkeypatch, results):
    """Runs selfcheck with checks returning `results` in turn; returns (exit code, pids killed)."""
    answers = iter(results)
    killed = []
    monkeypatch.setitem(selfcheck.CHECKS, "app", (lambda: next(answers), "uvicorn"))
    monkeypatch.setattr(selfcheck, "main_pids", lambda marker: [42])
    monkeypatch.setattr(selfcheck.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(selfcheck.time, "sleep", lambda s: None)
    monkeypatch.setattr(selfcheck, "say", lambda m: None)
    return selfcheck.main(["app"]), killed


def test_healthy_app_is_left_alone(monkeypatch):
    assert _run(monkeypatch, [True]) == (0, [])


def test_one_slow_answer_is_forgiven(monkeypatch):
    assert _run(monkeypatch, [False, False, True]) == (0, [])


def test_app_failing_every_check_is_stopped_for_docker_to_restart(monkeypatch):
    assert _run(monkeypatch, [False, False, False]) == (1, [(42, signal.SIGKILL)])
