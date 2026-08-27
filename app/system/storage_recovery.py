"""Bounded automatic recovery actions for critical storage pressure."""
from __future__ import annotations

import subprocess
from typing import Callable


RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return subprocess.CompletedProcess(arguments, 1, "", str(error))


def recover_storage(
    state: str,
    run: RunCommand = _run,
    *,
    resume_nonessential: bool = False,
) -> dict[str, object]:
    actions: list[str] = []
    if state not in {"critical", "emergency"}:
        if resume_nonessential:
            started = run(["systemctl", "start", "fieldmouse-backup.timer"])
            if started.returncode == 0:
                actions.append("backup_timer_resumed")
        return {"attempted": False, "actions": actions, "cleanup_succeeded": None}
    if state == "emergency":
        run(["systemctl", "stop", "fieldmouse-backup.timer"])
        actions.append("backup_timer_suspended")
    cleanup = run(["systemctl", "start", "fieldmouse-cleanup.service"])
    actions.append("cleanup_attempted")
    cleanup_succeeded = cleanup.returncode == 0
    if cleanup_succeeded:
        recorder = run(["systemctl", "is-active", "fieldmouse-recorder.service"])
        if recorder.returncode != 0:
            started = run(["systemctl", "start", "fieldmouse-recorder.service"])
            if started.returncode == 0:
                actions.append("recorder_started")
    return {
        "attempted": True,
        "actions": actions,
        "cleanup_succeeded": cleanup_succeeded,
    }
