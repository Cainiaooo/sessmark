# HerdR integration

[English](herdr.en.md) | [中文](herdr.md)

Requires Python 3.11+, HerdR 0.8.2+, and the official integration for the harness you use. The core CLI does not need those host conditions.

The TUI follows the OS language, or `SESSMARK_LANG=en` / `SESSMARK_LANG=zh`.

## Install and keybindings

Windows, from the sessmark repo root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ui]" -e adapters\herdr
herdr plugin link "$PWD\plugins\herdr"
herdr integration install grok
# Install the harness you actually use, e.g. herdr integration install codex
```

From GitHub (listed after the repo has the `herdr-plugin` topic):

```powershell
herdr plugin install Cainiaooo/sessmark/plugins/herdr
```

That install runs `plugins/herdr/bootstrap.py` (Python 3.11+ on `PATH`) and does not use a repo-root `.venv`. Local `plugin link` does not run build steps.

Add to `%APPDATA%\herdr\config.toml`. 0.8.2 binds `rename_tab` to `prefix+shift+t` by default;
move that first, then give the viewer that chord. If `[keys]` already exists, merge fields; do not declare the table twice:

```toml
[keys]
rename_tab = "prefix+shift+y"

[[keys.command]]
key = "prefix+t"
type = "plugin_action"
command = "sessmark.mark-windows"
description = "tag and note the current session"

[[keys.command]]
key = "prefix+shift+t"
type = "plugin_action"
command = "sessmark.ui-windows"
description = "browse marked sessions"

[[keys.command]]
key = "prefix+shift+c"
type = "plugin_action"
command = "sessmark.config-windows"
description = "edit sessmark tags, pipelines and prompts"
```

```powershell
herdr config check
herdr server reload-config
```

The Windows manifest calls PowerShell, which prefers `plugins/herdr/.venv` (marketplace install), then the checkout `.venv\Scripts\python.exe`, then `sessmark-herdr` on PATH. You do not need to activate a venv or change the HerdR server PATH.
Launch strips the Windows `\\?\` prefix HerdR may return, so Windows PowerShell 5.1 `Join-Path` works.
macOS/Linux uses `.venv/bin/python`; action ids are `sessmark.mark` / `sessmark.ui` and need system `python3`.
The two platforms use separate action/pane ids so the manifest has no duplicate names.

## Human path

In an Agent pane press `prefix+t`: `/` searches tag names or prompts, Space checks a tag, `n` adds a preset, `e` opens the vocabulary, Tab types one note, Enter / Ctrl+S saves atomically, Esc cancels. Enter or ↓ in search returns to the list; checks survive the filter; the footer shows selected tags and how many are hidden.
`prefix+shift+c` opens the vocabulary directly (you do not need the mark window first).
The mark window captures the target pane when it opens; before save it re-checks terminal and native identity. If a confirmed session changed, save is refused and you are asked to reopen.

`prefix+shift+t` opens the viewer: up/down to select; `/` live-searches notes, tags, paths, or IDs (space-separated AND); `tag:keep` matches that tag exactly. Time / `F2` cycles all, today, last 7 days; Agent / `F3` cycles sources; `Ctrl+L` clears filters; `r` reloads.
Enter on a row returns to a verified original Agent pane, or resumes in a new HerdR tab. `y` copies a readable summary (id / tags / notes / locator / prompt), not a PowerShell command.
`d` or Delete removes every mark on the selected session; the confirm dialog shows id, tags, and notes, and defaults to Cancel. After delete the filter is kept and the list refreshes; original chat files stay. If the row changed during confirm, refresh and confirm again.
Agents batch-read today's marks with `sessmark export --since today --json`. The UI does not edit old notes; remove a tag with the CLI.

All three popups use a short list plus full detail; wide terminals split left/right, narrow ones stack. `F4` focuses detail for scrolling; `Esc` returns to the list. Footer buttons are clickable; focus and the current row are highlighted. Prompt editing: `Alt+Enter` newline, `Ctrl+S` save.
Default popups use fixed cell sizes: mark / vocabulary `120 columns × 32 rows`, session browser `132 × 36`, instead of `92% × 88%`, so they do not go nearly fullscreen on a large display.

From a HerdR pane that already has the sessmark venv activated:

```powershell
sessmark-herdr tag review:problem
sessmark-herdr note "review this later"
sessmark-herdr sync --json
sessmark-herdr resume sm_SOME_ID --dry-run
```

`pane.agent_detected` / `pane.agent_status_changed` hooks fill in native identity for already-marked panes. The hook reads the pane in the event and does not use whatever is focused at that moment.
No HerdR call is made when nothing matches. Viewer startup and explicit `sync` also refresh marked rows on the current endpoint.
Pipelines can `sessmark-herdr sync` first, then use plain `sessmark list/context`; offline consumers do not call the host.

## Marketplace listing

HerdR lists public GitHub repositories tagged `herdr-plugin` that have a parseable `herdr-plugin.toml` on the default branch. There is no submission or review queue. This repo's manifest is `plugins/herdr/herdr-plugin.toml`. After the topic is added, wait about 30 minutes or push to `main`. See [Marketplace](https://herdr.dev/docs/marketplace/).

## Interface basis and limits

Based on the official [CLI reference](https://herdr.dev/docs/cli-reference/), [plugins](https://herdr.dev/docs/plugins/),
[socket API](https://herdr.dev/docs/socket-api/), and [configuration](https://herdr.dev/docs/configuration/).
All interaction goes through the CLI at `HERDR_BIN_PATH`; no direct socket or named pipe.
`pane get/current/list` default to JSON; the native reference is `agent_session: {source, agent, kind, value}`.
A popup has no pane ID; it reads `HERDR_PLUGIN_CONTEXT_JSON.focused_pane_id` or `HERDR_ACTIVE_PANE_ID`.
0.8.2 popup/overlay does not allow `--target-pane`; the mark entry pins the target only via `SESSMARK_TARGET_PANE`
and still verifies identity before open and before save.

A Grok native ID is enough for `grok --resume ID`. When the host only gives an ID, `transcript_path` is null;
cwd slugs are not invented. Passing a full path can fill in `~/.grok/sessions/<encoded-cwd>/<id>/chat_history.jsonl`.

If the original pane is gone and pending never bound, run `sessmark bind sm_ID --harness grok --session-id REAL_ID`.
Different HerdR endpoints, terminals, or native IDs do not focus the old pane.
Outside HerdR, use `sessmark resume`; the plugin does not need to be installed or started.

A real `plugin link` was run on HerdR 0.8.2 on 2026-09-06. That version has no `pane.updated` plugin event,
so agent detected/status changed is used, with explicit sync and viewer startup refresh as backup.
A user Grok report verified mark/viewer in the overlay, pending sync, and resume in a new tab after the pane closed.
Popup-argument and copy-command PATH issues from that report are fixed and covered by tests. Physical chords, IME inside the popup, and macOS still need acceptance.

### Host limit: Grok `/new`

The report: after `/new` in the same Grok process, HerdR may still return the old native ID. Local
`~/.grok/hooks/herdr-agent-state.ps1` prefers `GROK_SESSION_ID` and only reads the hook payload when that is empty.
sessmark cannot see a new session from the same host response, and `sync` will not correct the old ID.
Workaround: quit and restart Grok, or pass the real new native ID on the core CLI.
Notes already written onto the old native row are not migrated; `bind` does not rewrite an established native identity.
This tool does not edit HerdR-managed hooks; do not treat in-process `/new` as passing.
