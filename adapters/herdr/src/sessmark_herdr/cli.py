import argparse
import json
import os
import sqlite3
import sys

from sessmark import SessmarkError, Store
from sessmark.cli import add_storage, emit
from sessmark.config import Config, data_path
from sessmark.resume import execute, plan

from .adapter import Herdr


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    root = argparse.ArgumentParser(description="Optional HerdR adapter for sessmark")
    add_storage(root)
    commands = root.add_subparsers(dest="command", required=True)
    for name in (
        "tag",
        "untag",
        "note",
        "mark",
        "ui",
        "config",
        "open-mark",
        "open-ui",
        "open-config",
        "sync",
        "sync-event",
        "resume",
        "run-resume",
    ):
        p = commands.add_parser(name)
        add_storage(p)
        if name in ("tag", "untag"):
            p.add_argument("tags", nargs="+")
        if name == "note":
            p.add_argument("text")
        if name in ("tag", "untag", "note", "sync"):
            p.add_argument("--json", action="store_true")
        if name == "ui":
            p.add_argument("--tag", action="append", default=[])
        if name == "resume":
            p.add_argument("id")
            p.add_argument("--dry-run", action="store_true")
    args = root.parse_args(argv)
    host = Herdr()
    try:
        if args.command in ("open-mark", "open-ui", "open-config"):
            emit(host.open_popup(args.command.removeprefix("open-")))
            return 0
        with Store(
            getattr(args, "db", None) or data_path(), Config(getattr(args, "config", None))
        ) as store:
            if args.command in ("tag", "untag", "note", "mark"):
                selected = host.current()
                if args.command == "mark":
                    from sessmark.ui import mark_dialog

                    mark_dialog(store, selected, before_save=lambda: host.guard(selected))
                else:
                    result = store.mark(
                        **selected,
                        tags=args.tags if args.command == "tag" else (),
                        remove=args.tags if args.command == "untag" else (),
                        note=args.text if args.command == "note" else None,
                    )
                    emit(result) if args.json else print(result["id"])
            elif args.command in ("sync", "sync-event"):
                pane_id = None
                if args.command == "sync-event":
                    event = json.loads(os.environ.get("HERDR_PLUGIN_EVENT_JSON", "{}"))
                    payload = event.get("data", event)
                    pane_id = payload.get("pane_id") or payload.get("pane", {}).get("pane_id")
                    if not pane_id:
                        return 0
                emit(host.sync(store, pane_id))
            elif args.command == "resume":
                emit(host.open_session(store, args.id, args.dry_run))
            elif args.command == "run-resume":
                id = os.environ.get("SESSMARK_RESUME_ID")
                if not id:
                    raise SessmarkError("SESSMARK_RESUME_ID missing")
                return execute(plan(store.get(id)[0]))
            elif args.command == "ui":
                from sessmark.ui import viewer

                host.sync(store)
                viewer(store, args.tag, on_open=lambda id: host.open_session(store, id))
            elif args.command == "config":
                from sessmark.ui import config_dialog

                config_dialog(store.config)
        return 0
    except (SessmarkError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"sessmark-herdr: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        return 130
