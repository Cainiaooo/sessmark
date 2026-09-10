# sessmark

[English](README.md) | [中文](README.zh.md)

Tag Agent **session objects**, write notes, and emit reference packages that automation can resolve.
Does not modify Agent transcripts, call a model, or require HerdR. Python 3.11+; Windows first, with macOS/Linux path and terminal support.

Origin: [herdr-dev-env-template issue #1](https://github.com/Cainiaooo/herdr-dev-env-template/issues/1).
Implementation and environment-config repos are maintained separately.

The terminal UI and first-time vocabulary follow the OS language, or `SESSMARK_LANG=en` / `SESSMARK_LANG=zh`. Existing `templates.toml` files are left as-is.

## Install

`sessmark` is a user-level CLI. Data lives under `~/.local/share/sessmark/` (override with `XDG_DATA_HOME`), not in a project checkout. Not on PyPI yet. Do not install `sessmark-herdr` globally; the HerdR plugin ships its own runtime.

### Daily use (recommended)

Needs [uv](https://docs.astral.sh/uv/). The command lands in `~/.local/bin` (`%USERPROFILE%\.local\bin` on Windows), which should already be on `PATH`.

```powershell
cd path\to\sessmark
uv tool install -e ".[ui]"
sessmark --help
```

Same command on macOS/Linux. This is an editable install: source edits in this checkout apply without reinstalling. Re-run the same command if dependencies or extras change.

Pipeline-only (no TUI): `uv tool install -e .`

Uninstall: `uv tool uninstall sessmark`.

### Develop this repository

Tests, packaging, and local `herdr plugin link` still use the checkout `.venv`:

```powershell
cd path\to\sessmark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
.venv\Scripts\Activate.ps1
sessmark --help
```

macOS/Linux: `python3 -m venv .venv`, `source .venv/bin/activate`, then `python -m pip install -e '.[ui,dev]'`.
Activating the venv also puts `sessmark` on that shell's `PATH`; that does not replace the user-level install above.

## Use in any terminal

Pass a real native session ID. The tool will not guess “the newest file in this directory” as the current session.

```powershell
$id = sessmark tag review:problem --harness grok --session-id a1b2c3 --cwd D:\work\proj
sessmark note "tool timed out then looped; check backoff later" --id $id
sessmark tag prio:p0 --id $id
sessmark show $id
sessmark context $id --json
sessmark resume $id --dry-run
sessmark resume $id
```

Or `sessmark register --harness grok --session-id a1b2c3`, or set explicit context:

```powershell
$env:SESSMARK_HARNESS = 'grok'
$env:SESSMARK_SESSION_ID = 'a1b2c3'
sessmark tag keep
sessmark note "look this up later"
sessmark mark   # / live tag search, Space multi-select, Tab note, Enter save
sessmark ui     # / search notes/path/ID, F2 time, F3 agent, Enter resume, y copy summary
```

`SESSMARK_ID` binds an existing sessmark ID; explicit `--harness/--session-id` win over the env ID.
`--id` cannot be mixed with locator fields. The mark UI appends tags and one note; remove a tag with `untag`.
Delete every mark on a session: in `sessmark ui`, select the row, press `d` or click Delete. The confirm dialog defaults to Cancel. That removes tags, notes, and related rows for that sessmark ID; the original session / transcript files stay. CLI: `sessmark delete <sm_ID> --yes` (`--json` supported). After delete, the old sessmark ID cannot be read; marking the same original session again gets a new ID.

## Pipelines

`--json` is a JSON **array**; `--jsonl` is one object per line. Errors go to stderr and exit 2, and do not pollute stdout.

Agents reading today's marks (recommended):

```powershell
sessmark export --since today --json
```

If `sessmark` is not on `PATH`, the user-level install is missing. Do not guess a checkout `.venv` path. Agents working *in this repository* follow `AGENTS.md` (venv) instead.

Without `--json`, `export` prints a human summary. Narrow by tag: `export --tag review:problem --since today --json`.
`export --tag` filters both sessions and the pipeline; repeated `--tag` requires the session to have all of those tags, and chooses the prompt only among those tags. If more than one template still matches, JSON `prompt` is null.

Single-session context still works:

```powershell
sessmark list --tag review:problem --since today --json |
  ConvertFrom-Json | ForEach-Object {
    sessmark context $_.id --tag review:problem --json
  }
```

`today` is local midnight; `1d` is a rolling 24 hours. Also accepts timezone-aware ISO 8601, `24h`, `30m`.
Time uses the human `updated_at`; `--since` is inclusive, `--until` is exclusive. Repeated `--tag` is AND.
One session can belong to several pipelines; a single query still returns it once.

```powershell
sessmark tag harvest:doc --id $id
sessmark context $id --tag harvest:doc --json
sessmark context $id --template review-problem --json
```

If several tags map to different templates, omitting `--tag` / `--template` fails clearly. `keep` / `prio:p0` alone yield `prompt` null (`keep:archive` uses the archive pipeline).

The vocabulary (tags / pipelines / prompts) is personal config. You do not need a CLI command to add a preset.

In HerdR: `prefix+shift+c` opens the vocabulary window; in the mark window, `n` adds a tag and `e` opens the same editor.
`n`: tag name, empty prompt = lookup only (e.g. `keep`), filled prompt = pipeline (e.g. `review:ux`).
In the vocabulary window: `Enter` edits the prompt, `d` deletes, `o` opens `~/.config/sessmark/templates.toml` in the system editor.
Mark and vocabulary windows both support `/` or `Ctrl+F` to search tag names, pipelines, and prompts; `Ctrl+L` clears; `Enter` / `↓` in the search box return to results. Filtering does not drop checked tags.
Wide terminals split left/right; narrow ones stack. `F4` moves to the detail pane for long content, `Esc` returns to the list. Common actions also have clickable buttons. While editing a prompt, `Alt+Enter` inserts a newline and `Ctrl+S` saves.

The session browser searches all historical notes, tags, directories, and IDs; space-separated words are AND. `tag:review:problem` matches that tag exactly. Time (`F2`) cycles all / today / last 7 days; Agent (`F3`) cycles sources; `Ctrl+L` resets filters; `r` reloads.

```powershell
sessmark config --ui              # same TUI
sessmark config                   # path, vocabulary, and routes
sessmark config --init            # write an editable copy; refuses to overwrite
sessmark config --add-tag later   # optional: append from a script
```

Default vocabulary:

| tag | pipeline |
| --- | --- |
| `review:problem` | Deferred problem review |
| `fix:tool` | Review in-house tools used this session |
| `review:context` | Review whether memory docs, skills, and other context drifted |
| `write:doc` | Write docs related to this session |
| `harvest:asset` | Capture reusable technical assets |
| `harvest:doc` | Extract personal technical notes (do not write back to the project README) |
| `keep:archive` | Archive note for an important session |
| `fix:skill` | Change skill behavior |
| `fix:context` | Fill project context / rule gaps |
| `keep` | Lookup only, no pipeline |
| `prio:p0` | Do this tonight, no pipeline |

Unknown tags error on add and filter; tags already stored on sessions can still be removed with `untag` after they leave the vocabulary. The original issue's `prio:p1` is not in the default table. Templates do not interpolate notes, paths, or transcripts. Do not edit the repo `defaults.toml` / `defaults.en.toml` unless you are changing the default vocabulary.

## Optional HerdR adapter

```powershell
.venv\Scripts\python.exe -m pip install -e adapters\herdr
herdr plugin link $PWD\plugins\herdr
```

In a HerdR pane with integration configured you can run `sessmark-herdr tag keep` directly.
`prefix+t` to mark and `prefix+shift+t` for the viewer: see [HerdR integration](docs/herdr.en.md) ([中文](docs/herdr.md)).
HerdR 0.8.2 uses `prefix+shift+t` for `rename_tab` by default; move that binding first. The integration doc has the full key config.
Without the adapter package, every core `sessmark` command still works; the core neither imports the adapter nor checks `HERDR_*`.

### Plugin marketplace

HerdR's [marketplace](https://herdr.dev/plugins/) is an automatic index of public GitHub repos, not a review queue. There is no submission form.

To be listed:

1. The repository is **public**.
2. Add the GitHub topic **`herdr-plugin`**.
3. The default branch contains at least one `herdr-plugin.toml` whose required metadata (`id`, `name`, `version`, `min_herdr_version`) parses. The file may live at the repo root or in a subdirectory.

This repo's manifest is [`plugins/herdr/herdr-plugin.toml`](plugins/herdr/herdr-plugin.toml). The index refreshes about every 30 minutes and again when `main` moves. Forks, archived repos, and invalid manifests are skipped. A listing is not a HerdR review; see HerdR's [trust guidance](https://herdr.dev/docs/plugins/#trust-and-security).

Install from GitHub (after the topic is on the public repo):

```powershell
herdr plugin install Cainiaooo/sessmark/plugins/herdr
```

Install runs `plugins/herdr/bootstrap.py`, which creates a plugin-local venv and installs `sessmark[ui]` plus `sessmark-herdr` from the same checkout. Python 3.11+ must be on `PATH` (`python` on Windows, `python3` on macOS/Linux). Local development still uses `herdr plugin link` and the repo `.venv`; link does not run build steps.

## Library API and layout

```python
from pathlib import Path
from sessmark import Locator, Store

with Store(Path.home() / ".local/share/sessmark/index.sqlite") as store:
    row = store.mark(locator=Locator("grok", "a1b2c3"),
                     cwd=str(Path.cwd()), tags=["keep"], note="look this up later")
    package = store.context(row["id"])
```

| path | role |
| --- | --- |
| `src/sessmark` | Library, CLI, optional TUI; zero HerdR imports |
| `adapters/herdr` | Separate Python distribution; pane identity, refresh, focus, new tabs |
| `plugins/herdr` | HerdR manifest and Windows/macOS launchers |
| `schemas` | `sessmark.context.v1` and session JSON Schema |
| `tests`, `adapters/herdr/tests` | Store, CLI, UI input, adapter contract tests |

Semantics: [design contract](docs/design.md) (Chinese). Verification: [testing notes](docs/testing.md) (Chinese).
Known limit: after Grok in-process `/new`, the host may still report the old ID; restart Grok or pass the new ID to the core CLI until the hook is fixed.

## Storage and locators

Data: `${XDG_DATA_HOME:-~/.local/share}/sessmark/index.sqlite`. Config: `${XDG_CONFIG_HOME:-~/.config}/sessmark/templates.toml`.
On Windows, a copy is taken once from `%LOCALAPPDATA%\sessmark` / `%APPDATA%\sessmark`, including Microsoft Store Python `LocalCache` copies, unless `XDG_DATA_HOME` / `XDG_CONFIG_HOME` is set. Store Python virtualizes AppData, so a user-level CLI and a Store-based venv cannot share a database that lives there.
Override with `--db` / `SESSMARK_DB` and `--config` / `SESSMARK_CONFIG`.

Native identity is `(harness, session_id)`; path is an optional hint. Grok/Claude/Codex/OpenCode/Pi get default resume argv; other harnesses can pass `--resume-json`.
The Windows executor requires a native exe; if the install is only a `.cmd` wrapper, pass a full argv such as `node.exe + CLI script + args`.
`resume --dry-run` or `resume --json` only shows the plan; a normal `resume` starts the process.

If HerdR has not provided a native ID yet, the row is pending; when the ID appears, tags/notes merge in a transaction and old sessmark IDs stay aliases until the user deletes that mark.
If the original pane is already gone:

```powershell
sessmark bind sm_OLD_ID --harness grok --session-id REAL_ID
```

Context always references the transcript; `partial: true` means the original session may still change. Local notes and paths appear as stored; the consumer decides redaction and permission before sending anything off-box. Nothing is uploaded automatically.
