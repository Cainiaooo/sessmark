import json
import os
import subprocess
from pathlib import Path

from sessmark import Binding, Locator, SessmarkError
from sessmark.model import nonempty
from sessmark.resume import native_command


class Herdr:
    def __init__(self, env=None, runner=subprocess.run):
        self.env = dict(os.environ if env is None else env)
        self.runner = runner
        self.binary = self.env.get("HERDR_BIN_PATH", "herdr")
        self.endpoint = self.env.get("HERDR_SOCKET_PATH") or self.env.get(
            "HERDR_SESSION", "default"
        )

    def call(self, *args):
        try:
            result = self.runner(
                [self.binary, *args],
                env=self.env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SessmarkError(f"Cannot call HerdR: {exc}") from exc
        if result.returncode:
            raise SessmarkError(
                f"HerdR {' '.join(args[:2])}: {result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            body = json.loads(result.stdout)
        except ValueError as exc:
            raise SessmarkError("HerdR returned invalid JSON") from exc
        if not isinstance(body, dict) or body.get("error"):
            raise SessmarkError(f"HerdR error: {body}")
        return body.get("result", body)

    def context(self):
        try:
            value = json.loads(self.env.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
        except ValueError as exc:
            raise SessmarkError("Invalid HERDR_PLUGIN_CONTEXT_JSON") from exc
        if not isinstance(value, dict):
            raise SessmarkError("HERDR_PLUGIN_CONTEXT_JSON must be an object")
        return value

    def pane(self, pane_id=None):
        if pane_id is None:
            # Popup launch context wins over the process pane, which can be an overlay.
            pane_id = (
                self.env.get("SESSMARK_TARGET_PANE")
                or self.context().get("focused_pane_id")
                or self.env.get("HERDR_ACTIVE_PANE_ID")
                or self.env.get("HERDR_PANE_ID")
            )
        result = self.call("pane", "get", pane_id) if pane_id else self.call("pane", "current")
        pane = result.get("pane", result)
        if not isinstance(pane, dict) or not pane.get("pane_id"):
            raise SessmarkError("HerdR response has no pane identity")
        if pane_id and pane["pane_id"] != pane_id:
            raise SessmarkError("HerdR returned a different pane")
        return pane

    def selection(self, pane):
        pane_id = nonempty(pane.get("pane_id"), "pane_id")
        generation = nonempty(pane.get("terminal_id"), "terminal_id")
        ref = pane.get("agent_session") or {}
        if not isinstance(ref, dict):
            raise SessmarkError("Unsupported agent_session shape")
        agent = ref.get("agent") or pane.get("agent")
        if not agent:
            raise SessmarkError("No detected agent; enable the harness's HerdR integration")
        agent = agent.lower()
        if pane.get("agent") and pane["agent"].lower() != agent:
            raise SessmarkError(
                "Detected harness and native reference disagree; retry after integration refresh"
            )
        native_id, path = None, None
        if ref:
            kind, value = ref.get("kind"), ref.get("value")
            nonempty(value, "agent_session.value")
            if kind == "id":
                native_id = value
            elif kind == "path":
                path = value
            else:
                raise SessmarkError(f"Unsupported agent_session kind: {kind}")
        # Explicit reported hints only. Never guess a cwd slug or pick the latest file.
        path = path or ref.get("transcript_path") or pane.get("agent_session_path")
        cwd = pane.get("foreground_cwd") or pane.get("cwd")
        if not cwd or not Path(cwd).is_absolute():
            raise SessmarkError("HerdR did not report an absolute agent cwd")
        binding = Binding(
            "herdr",
            json.dumps([self.endpoint, pane_id]),
            generation,
            {
                "endpoint": self.endpoint,
                "pane_id": pane_id,
                "terminal_id": generation,
                "workspace_id": pane.get("workspace_id"),
                "tab_id": pane.get("tab_id"),
                "ref": ref,
            },
        )
        return {
            "locator": Locator(agent, native_id, path, native_command(agent, native_id, path)),
            "cwd": cwd,
            "binding": binding,
        }

    def current(self):
        return self.selection(self.pane())

    def guard(self, selected):
        fresh = self.selection(self.pane(selected["binding"].metadata["pane_id"]))
        old, new = selected["locator"], fresh["locator"]
        if (
            fresh["binding"].generation != selected["binding"].generation
            or old.harness != new.harness
            or (old.session_id and old.session_id != new.session_id)
            or (
                not old.session_id
                and old.transcript_path
                and old.transcript_path != new.transcript_path
            )
        ):
            raise SessmarkError("Pane session changed while editing; close and reopen the marker")
        return fresh

    def sync(self, store, pane_id=None):
        bindings = [
            b
            for b in store.bindings("herdr")
            if b["metadata"].get("endpoint") == self.endpoint
            and (pane_id is None or b["metadata"].get("pane_id") == pane_id)
        ]
        if not bindings:
            return []
        if pane_id:
            panes = [self.pane(pane_id)]
        else:
            panes = self.call("pane", "list").get("panes", [])
        known = {b["metadata"]["pane_id"]: b for b in bindings}
        results = []
        for pane in panes:
            if pane.get("pane_id") not in known:
                continue
            if not pane.get("agent"):
                continue  # An exited agent does not prevent browsing stored marks.
            selected = self.selection(pane)
            id = store.observe(**selected)
            if id:
                results.append(id)
        return sorted(set(results))

    def open_popup(self, mode):
        entrypoint = mode + ("-windows" if os.name == "nt" else "")
        args = [
            "plugin",
            "pane",
            "open",
            "--plugin",
            "sessmark",
            "--entrypoint",
            entrypoint,
            "--placement",
            "popup",
            "--width",
            "85%",
            "--height",
            "80%",
        ]
        if mode == "mark":
            pane = self.pane()
            self.selection(pane)  # Fail before covering the user's terminal.
            args += [
                "--target-pane",
                pane["pane_id"],
                "--env",
                f"SESSMARK_TARGET_PANE={pane['pane_id']}",
            ]
        return self.call(*args)

    def open_session(self, store, id, dry_run=False):
        session = store.get(id)[0]
        for b in store.bindings("herdr"):
            if b["session"] != session["id"] or b["metadata"].get("endpoint") != self.endpoint:
                continue
            try:
                fresh = self.selection(self.pane(b["metadata"]["pane_id"]))
            except SessmarkError:
                continue
            if fresh["binding"].generation != b["generation"]:
                continue
            saved = session["locator"]
            live = fresh["locator"]
            matches = (
                saved["harness"] == live.harness
                and saved["session_id"] is not None
                and saved["session_id"] == live.session_id
            )
            if not matches:
                continue  # Pending identity cannot prove the old conversation is still live.
            launch = {"action": "focus", "pane_id": b["metadata"]["pane_id"]}
            if not dry_run:
                self.call("agent", "focus", launch["pane_id"])
            return launch
        from sessmark.resume import plan

        launch = plan(session)
        if not dry_run:
            entrypoint = "resume-windows" if os.name == "nt" else "resume"
            args = [
                "plugin",
                "pane",
                "open",
                "--plugin",
                "sessmark",
                "--entrypoint",
                entrypoint,
                "--placement",
                "tab",
                "--cwd",
                launch["cwd"],
                "--env",
                f"SESSMARK_RESUME_ID={session['id']}",
                "--env",
                f"SESSMARK_DB={store.path.resolve()}",
            ]
            if store.config.path.exists():
                args += ["--env", f"SESSMARK_CONFIG={store.config.path.resolve()}"]
            self.call(*args)
        return {"action": "resume", **launch}
