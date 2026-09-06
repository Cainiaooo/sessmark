import os
import re
import sys
import tomllib
from importlib.resources import files
from pathlib import Path

from .model import SessmarkError


def data_path() -> Path:
    if value := os.environ.get("SESSMARK_DB"):
        return Path(value).expanduser()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return root / "sessmark/index.sqlite"


def config_path() -> Path:
    if value := os.environ.get("SESSMARK_CONFIG"):
        return Path(value).expanduser()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "sessmark/templates.toml"


class Config:
    def __init__(self, path: Path | None = None):
        explicit = path is not None or bool(os.environ.get("SESSMARK_CONFIG"))
        self.path = path or config_path()
        try:
            self.data = tomllib.loads(
                files("sessmark").joinpath("defaults.toml").read_text("utf-8")
            )
            if self.path.exists() or explicit:
                with self.path.open("rb") as stream:
                    self.data = tomllib.load(stream)
        except (OSError, ValueError) as exc:
            raise SessmarkError(f"Cannot read config {self.path}: {exc}") from exc
        tags = self.data.get("allowed_tags")
        if self.data.get("schema") != 1 or not isinstance(tags, list) or not tags:
            raise SessmarkError("Config requires schema = 1 and a nonempty allowed_tags array")
        if any(
            not isinstance(t, str) or not re.fullmatch(r"[a-z0-9]+(?::[a-z0-9_-]+)*", t)
            for t in tags
        ) or len(set(tags)) != len(tags):
            raise SessmarkError("allowed_tags must contain distinct lowercase tag names")
        self.tags = tuple(tags)
        self.routes = self.data.get("routes", {})
        self.templates = self.data.get("templates", {})
        if not isinstance(self.routes, dict) or not isinstance(self.templates, dict):
            raise SessmarkError("routes and templates must be TOML tables")
        for name, template in self.templates.items():
            if not isinstance(template, dict) or not isinstance(template.get("text"), str):
                raise SessmarkError(f"Template {name} requires text")
        for tag, template in self.routes.items():
            if (
                tag not in self.tags
                or not isinstance(template, str)
                or template not in self.templates
            ):
                raise SessmarkError(f"Invalid route: {tag} -> {template}")

    def validate_tags(self, tags):
        unknown = set(tags) - set(self.tags)
        if unknown:
            raise SessmarkError(f"Unknown tags: {', '.join(sorted(unknown))}; edit {self.path}")

    def prompt(self, tags, template: str | None = None, tag: str | None = None):
        self.validate_tags(tags)
        if tag is not None:
            self.validate_tags([tag])
            if tag not in tags:
                raise SessmarkError(f"Session does not have tag: {tag}")
            tags = [tag]
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
