import argparse
import json
import os
import sqlite3
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .config import Config, config_path, data_path
from .model import Locator, SessmarkError, since_time
from .resume import execute, native_command, plan
from .store import Store


def emit(value, jsonl=False):
    if jsonl:
        for row in value:
            print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def add_storage(parser):
    parser.add_argument("--db", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS)


def target_arguments(parser):
    parser.add_argument("--id", help="sessmark ID, or SESSMARK_ID")
    parser.add_argument("--harness", help="native harness name, or SESSMARK_HARNESS")
    parser.add_argument("--session-id", help="native session ID, or SESSMARK_SESSION_ID")
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--transcript-path", type=Path)
    parser.add_argument(
        "--resume-json", help='explicit argv JSON, e.g. ["my-agent", "resume", "id"]'
    )


def target(args):
    explicit_native = args.harness is not None or args.session_id is not None
    id = (
        args.id
        if args.id is not None
        else (None if explicit_native else os.environ.get("SESSMARK_ID"))
    )
    harness = args.harness or os.environ.get("SESSMARK_HARNESS")
    native_id = args.session_id or os.environ.get("SESSMARK_SESSION_ID")
    if id:
        if explicit_native or args.cwd or args.transcript_path or args.resume_json:
            raise SessmarkError("--id cannot be combined with locator fields")
        return {"id": id}
    if not harness or not native_id:
        raise SessmarkError("Use --id, or --harness + --session-id; for HerdR use sessmark-herdr")
    path = str(args.transcript_path.expanduser().resolve()) if args.transcript_path else None
    command = native_command(harness, native_id, path)
    if args.resume_json:
        try:
            command = json.loads(args.resume_json)
        except ValueError as exc:
            raise SessmarkError("--resume-json must be a JSON argv array") from exc
        if not isinstance(command, list) or not command:
            raise SessmarkError("--resume-json must be a nonempty argv array")
    return {
        "locator": Locator(harness, native_id, path, tuple(command)),
        "cwd": str((args.cwd or Path.cwd()).expanduser().resolve()),
    }


def parser():
    root = argparse.ArgumentParser(
        description="Session tags, notes and references; no host required."
    )
    root.add_argument("--version", action="version", version=__version__)
    add_storage(root)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("register", "tag", "untag", "note", "mark", "bind"):
        p = commands.add_parser(name)
        add_storage(p)
        target_arguments(p)
        p.add_argument("--json", action="store_true")
        if name in ("tag", "untag"):
            p.add_argument("tags", nargs="+")
        elif name == "note":
            p.add_argument("text")
        elif name == "bind":
            p.add_argument("target_id")
    p = commands.add_parser("list")
    add_storage(p)
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--since")
    p.add_argument("--until")
    formats = p.add_mutually_exclusive_group()
    formats.add_argument("--json", action="store_true", help="JSON array")
    formats.add_argument("--jsonl", action="store_true", help="one object per line")
    for name in ("show", "context", "resume"):
        p = commands.add_parser(name)
        add_storage(p)
        p.add_argument("id")
        p.add_argument("--json", action="store_true")
        if name == "context":
            p.add_argument("--template")
            p.add_argument("--tag")
        elif name == "resume":
            p.add_argument("--dry-run", action="store_true")
    p = commands.add_parser("ui")
    add_storage(p)
    p.add_argument("--tag", action="append", default=[])
    p = commands.add_parser("config")
    add_storage(p)
    p.add_argument("--init", action="store_true", help="write editable defaults; never overwrite")
    return root


def run(args):
    if args.command == "config":
        path = getattr(args, "config", None) or config_path()
        if args.init:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(files("sessmark").joinpath("defaults.toml").read_text("utf-8"))
        cfg = Config(path if args.init or getattr(args, "config", None) is not None else None)
        emit(
            {
                "config": str(path),
                "db": str(getattr(args, "db", None) or data_path()),
                "allowed_tags": cfg.tags,
                "routes": cfg.routes,
            }
        )
        return 0
    cfg = Config(getattr(args, "config", None))
    with Store(getattr(args, "db", None) or data_path(), cfg) as store:
        if args.command in ("register", "tag", "untag", "note", "mark", "bind"):
            selected = target(args)
            if args.command == "bind":
                if "locator" not in selected:
                    raise SessmarkError("bind requires --harness and --session-id")
                result = store.bind(
                    args.target_id, selected["locator"], selected["cwd"] if args.cwd else None
                )
                emit(result) if args.json else print(result["id"])
                return 0
            if args.command == "mark":
                from .ui import mark_dialog

                mark_dialog(store, selected)
                return 0
            result = store.mark(
                **selected,
                tags=args.tags if args.command == "tag" else (),
                remove=args.tags if args.command == "untag" else (),
                note=args.text if args.command == "note" else None,
            )
            emit(result) if args.json else print(result["id"])
        elif args.command == "list":
            rows = store.list(
                args.tag,
                since_time(args.since) if args.since else None,
                since_time(args.until) if args.until else None,
            )
            if args.json or args.jsonl:
                emit(rows, args.jsonl)
            else:
                for row in rows:
                    print(
                        f"{row['id']}  {row['agent']}  {','.join(row['tags'])}  {row['notes_preview']}"
                    )
        elif args.command == "context":
            result = store.context(args.id, args.template, args.tag)
            if args.json:
                emit(result)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "show":
            session, notes = store.get(args.id)
            emit({"session": session, "notes": notes})
        elif args.command == "resume":
            launch = plan(store.get(args.id)[0])
            if args.dry_run or args.json:
                emit(launch)
            else:
                return execute(launch)
        elif args.command == "ui":
            from .ui import viewer

            return viewer(store, tags=args.tag) or 0
    return 0


def main(argv=None):
    # Native Windows pipelines must preserve Chinese notes without depending on a console code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        return run(parser().parse_args(argv))
    except (SessmarkError, OSError, sqlite3.Error) as exc:
        print(f"sessmark: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        return 130
