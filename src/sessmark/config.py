import json
import os
import re
import shutil
import sys
import tomllib
from importlib.resources import files
from pathlib import Path

from .model import SessmarkError

# Microsoft Store Python redirects AppData into the package LocalCache.
_STORE_CACHE = re.compile(
    r"[/\\]Packages[/\\]PythonSoftwareFoundation\.[^/\\]+[/\\]LocalCache[/\\](Local|Roaming)",
    re.IGNORECASE,
)


def _windows_root(env_name: str, fallback: Path) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        return fallback
    path = Path(raw)
    if _STORE_CACHE.search(str(path)):
        home = Path(os.environ.get("USERPROFILE", str(Path.home())))
        return home / ("AppData/Local" if env_name == "LOCALAPPDATA" else "AppData/Roaming")
    return path


def _migrate_sidecar(target: Path, cached: Path):
    if cached.resolve() == target.resolve() or target.exists() or not cached.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, target)


def data_path() -> Path:
    if value := os.environ.get("SESSMARK_DB"):
        return Path(value).expanduser()
    if sys.platform == "win32":
        root = _windows_root("LOCALAPPDATA", Path.home() / "AppData/Local")
        target = root / "sessmark/index.sqlite"
        cached = Path(os.environ.get("LOCALAPPDATA", "")) / "sessmark/index.sqlite"
        if os.environ.get("LOCALAPPDATA"):
            _migrate_sidecar(target, cached)
        return target
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return root / "sessmark/index.sqlite"


def config_path() -> Path:
    if value := os.environ.get("SESSMARK_CONFIG"):
        return Path(value).expanduser()
    if sys.platform == "win32":
        root = _windows_root("APPDATA", Path.home() / "AppData/Roaming")
        target = root / "sessmark/templates.toml"
        cached = Path(os.environ.get("APPDATA", "")) / "sessmark/templates.toml"
        if os.environ.get("APPDATA"):
            _migrate_sidecar(target, cached)
        return target
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "sessmark/templates.toml"


TAG_RE = re.compile(r"[a-z0-9]+(?::[a-z0-9_-]+)*")
ROUTE_RE = re.compile(r"[A-Za-z0-9_-]+")


def default_route(tag: str) -> str:
    return tag.replace(":", "-")


def dump_config(data: dict) -> str:
    tags = ", ".join(json.dumps(tag, ensure_ascii=False) for tag in data["allowed_tags"])
    lines = [
        "# sessmark vocabulary. schema = 1",
        "# tags: lowercase, optional :segments   (review:ux)",
        "# routes map a tag to a template; templates hold the pipeline prompt.",
        f"schema = {int(data['schema'])}",
        f"allowed_tags = [{tags}]",
        "",
        "[routes]",
    ]
    for tag, template in data["routes"].items():
        lines.append(f"{json.dumps(tag, ensure_ascii=False)} = {json.dumps(template)}")
    for name, body in data["templates"].items():
        key = name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)
        lines.append("")
        lines.append(f"[templates.{key}]")
        lines.append(f"text = {json.dumps(body['text'], ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


class Config:
    def __init__(self, path: Path | None = None):
        explicit = path is not None or bool(os.environ.get("SESSMARK_CONFIG"))
        self.path = path or config_path()
        try:
            data = tomllib.loads(files("sessmark").joinpath("defaults.toml").read_text("utf-8"))
            if self.path.exists() or explicit:
                with self.path.open("rb") as stream:
                    data = tomllib.load(stream)
        except (OSError, ValueError) as exc:
            raise SessmarkError(f"Cannot read config {self.path}: {exc}") from exc
        self._apply(data)

    def _apply(self, data: dict):
        tags = data.get("allowed_tags")
        if data.get("schema") != 1 or not isinstance(tags, list) or not tags:
            raise SessmarkError("Config requires schema = 1 and a nonempty allowed_tags array")
        if any(not isinstance(t, str) or not TAG_RE.fullmatch(t) for t in tags) or len(
            set(tags)
        ) != len(tags):
            raise SessmarkError("allowed_tags must contain distinct lowercase tag names")
        routes = data.get("routes", {})
        templates = data.get("templates", {})
        if not isinstance(routes, dict) or not isinstance(templates, dict):
            raise SessmarkError("routes and templates must be TOML tables")
        for name, template in templates.items():
            if not isinstance(template, dict) or not isinstance(template.get("text"), str):
                raise SessmarkError(f"Template {name} requires text")
        for tag, template in routes.items():
            if tag not in tags or not isinstance(template, str) or template not in templates:
                raise SessmarkError(f"Invalid route: {tag} -> {template}")
        self.data = data
        self.tags = tuple(tags)
        self.routes = routes
        self.templates = templates

    def _commit(self, tags, routes, templates):
        data = {"schema": 1, "allowed_tags": list(tags), "routes": routes, "templates": templates}
        self._apply(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(dump_config(data), encoding="utf-8")

    def ensure_user_file(self):
        if not self.path.exists():
            self._commit(self.tags, dict(self.routes), {k: dict(v) for k, v in self.templates.items()})

    def reload(self):
        try:
            with self.path.open("rb") as stream:
                data = tomllib.load(stream)
        except (OSError, ValueError) as exc:
            raise SessmarkError(f"Cannot read config {self.path}: {exc}") from exc
        self._apply(data)

    def validate_tags(self, tags):
        unknown = set(tags) - set(self.tags)
        if unknown:
            raise SessmarkError(f"Unknown tags: {', '.join(sorted(unknown))}; add them in the sessmark vocabulary")

    def prompt(self, tags, template: str | None = None, tag: str | None = None):
        if tag is not None:
            self.validate_tags([tag])
            if tag not in tags:
                raise SessmarkError(f"Session does not have tag: {tag}")
            tags = [tag]
        else:
            tags = [item for item in tags if item in self.tags]
        if template is None:
            matches = sorted({self.routes[t] for t in tags if t in self.routes})
            if len(matches) > 1:
                raise SessmarkError("Multiple prompt routes; select --tag or --template explicitly")
            template = matches[0] if matches else None
        if template is None:
            return None
        if template not in self.templates:
            raise SessmarkError(f"Unknown template: {template}")
        return {"template_id": template, "text": self.templates[template]["text"]}

    def add_tag(self, tag: str, *, route: str | None = None, text: str | None = None):
        if not TAG_RE.fullmatch(tag):
            raise SessmarkError("tag must be lowercase letters, digits, and optional :segments")
        if tag in self.tags:
            raise SessmarkError(f"Tag already exists: {tag}")
        if (route is None) != (text is None):
            raise SessmarkError("Pipeline tags need both --route and --text; omit both for keep-style tags")
        tags = [*self.tags, tag]
        routes = dict(self.routes)
        templates = {name: dict(body) for name, body in self.templates.items()}
        if route is not None:
            if not ROUTE_RE.fullmatch(route):
                raise SessmarkError("route/template id must be letters, digits, _ or -")
            if not text.strip():
                raise SessmarkError("template text must be nonempty")
            if route in templates:
                raise SessmarkError(f"Template already exists: {route}")
            routes[tag] = route
            templates[route] = {"text": text.strip()}
        self._commit(tags, routes, templates)

    def set_prompt(self, tag: str, text: str, *, route: str | None = None):
        if tag not in self.tags:
            raise SessmarkError(f"Unknown tag: {tag}")
        text = text.strip()
        routes = dict(self.routes)
        templates = {name: dict(body) for name, body in self.templates.items()}
        if not text:
            old = routes.pop(tag, None)
            if old and old not in routes.values():
                templates.pop(old, None)
        else:
            name = route or routes.get(tag) or default_route(tag)
            if not ROUTE_RE.fullmatch(name):
                raise SessmarkError("route/template id must be letters, digits, _ or -")
            if tag not in routes and name in templates:
                raise SessmarkError(f"Template already exists: {name}")
            old = routes.get(tag)
            routes[tag] = name
            templates[name] = {"text": text}
            if old and old != name and old not in routes.values():
                templates.pop(old, None)
        self._commit(self.tags, routes, templates)

    def remove_tag(self, tag: str):
        if tag not in self.tags:
            raise SessmarkError(f"Unknown tag: {tag}")
        if len(self.tags) == 1:
            raise SessmarkError("Cannot remove the last tag")
        tags = [item for item in self.tags if item != tag]
        routes = dict(self.routes)
        templates = {name: dict(body) for name, body in self.templates.items()}
        old = routes.pop(tag, None)
        if old and old not in routes.values():
            templates.pop(old, None)
        self._commit(tags, routes, templates)
