"""Install sessmark[ui] and sessmark-herdr into a plugin-local venv."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def plugin_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def repo_root(plugin_root: Path) -> Path:
    return plugin_root.parent.parent


def main() -> int:
    plugin_root = Path(__file__).resolve().parent
    repo = repo_root(plugin_root)
    core = repo / "pyproject.toml"
    adapter = repo / "adapters" / "herdr" / "pyproject.toml"
    if not core.is_file() or not adapter.is_file():
        print(
            "sessmark sources missing; install from Cainiaooo/sessmark "
            "(herdr plugin install Cainiaooo/sessmark/plugins/herdr)",
            file=sys.stderr,
        )
        return 1
    python = plugin_python(plugin_root)
    if not python.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(plugin_root / ".venv")])
    subprocess.check_call(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-e",
            str(repo) + "[ui]",
            "-e",
            str(adapter.parent),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
