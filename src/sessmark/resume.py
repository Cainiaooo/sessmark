"""Native launch plans. No host import, shell interpolation, or transcript parsing."""

import os
import shutil
import subprocess
from pathlib import Path

from .model import Locator, SessmarkError


def native_command(harness: str, session_id: str | None, path: str | None = None):
    value = session_id
    if harness == "pi":
        value = value or path
    if not value:
        return ()
    flags = {
        "grok": "--resume",
        "claude": "--resume",
        "codex": "resume",
        "opencode": "--session",
        "pi": "--session",
    }
    return (harness, flags[harness], value) if harness in flags else ()


def plan(session):
    locator = Locator(
        **{
            k: session["locator"][k]
            for k in ("harness", "session_id", "transcript_path", "resume_cmd")
        }
    )
    command = locator.resume_cmd or native_command(
        locator.harness, locator.session_id, locator.transcript_path
    )
    if not command:
        raise SessmarkError(
            "No resume command; register a native ID or explicit --resume-json argv"
        )
    return {"cwd": session["cwd"], "argv": list(command)}


def execute(launch):
    if not Path(launch["cwd"]).is_dir():
        raise SessmarkError(f"Session working directory is unavailable: {launch['cwd']}")
    argv = launch["argv"]
    executable = shutil.which(argv[0])
    if executable is None:
        raise SessmarkError(f"Resume executable is not on PATH: {argv[0]}")
    # Windows can implicitly dispatch .cmd/.bat through cmd.exe even with shell=False.
    # Require a real executable to keep session IDs and custom args literal.
    if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat"):
        raise SessmarkError("Windows resume requires an .exe (or explicit node.exe + script argv)")
    return subprocess.call([executable, *argv[1:]], cwd=launch["cwd"], shell=False)
