# sessmark HerdR plugin

[English](../../README.md) | [中文](../../README.zh.md)

Session tags and notes for coding agents. Manifest: `herdr-plugin.toml`.

```powershell
herdr plugin install Cainiaooo/sessmark/plugins/herdr
```

Needs Python 3.11+ on `PATH` during install (`python` on Windows, `python3` on macOS/Linux). Install creates a plugin-local venv via `bootstrap.py`.

Local checkout:

```powershell
python -m pip install -e ".[ui]" -e adapters/herdr
herdr plugin link "$PWD/plugins/herdr"
```

UI language follows the OS, or `SESSMARK_LANG=en` / `SESSMARK_LANG=zh`. Keys and host notes: [HerdR integration](../../docs/herdr.en.md) ([中文](../../docs/herdr.md)).

This directory is what the [HerdR marketplace](https://herdr.dev/plugins/) indexes after the GitHub topic `herdr-plugin` is set on the public repo.
