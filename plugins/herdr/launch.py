"""macOS/Linux launcher for a source checkout or a separately installed adapter."""

import subprocess
import sys
from pathlib import Path

python = Path(__file__).resolve().parents[2] / ".venv/bin/python"
command = [str(python), "-m", "sessmark_herdr"] if python.exists() else ["sessmark-herdr"]
raise SystemExit(subprocess.call([*command, *sys.argv[1:]], shell=False))
