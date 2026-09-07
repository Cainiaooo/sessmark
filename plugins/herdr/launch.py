"""macOS/Linux launcher for a marketplace install or a source checkout."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
plugin = root / ".venv/bin/python"
project = root.parents[1] / ".venv/bin/python"
python = plugin if plugin.exists() else project if project.exists() else None
command = [str(python), "-m", "sessmark_herdr"] if python else ["sessmark-herdr"]
raise SystemExit(subprocess.call([*command, *sys.argv[1:]], shell=False))
