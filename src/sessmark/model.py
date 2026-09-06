import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


class SessmarkError(ValueError):
    """An actionable input, identity, or configuration error."""


def nonempty(value: str, name: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SessmarkError(f"{name} must be a nonempty string (max {limit} characters)")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise SessmarkError(f"{name} cannot contain control characters")
    return value


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def since_time(value: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise SessmarkError("now must include a timezone")
    if value == "today":
        # Convert naive local midnight independently: today's UTC offset can differ
        # from the current offset across a daylight-saving transition.
        midnight = datetime.combine(now.astimezone().date(), datetime.min.time())
        result = midnight.astimezone()
    elif match := re.fullmatch(r"(\d+)([dhm])", value):
        amount, unit = match.groups()
        result = now - timedelta(seconds=int(amount) * {"d": 86400, "h": 3600, "m": 60}[unit])
    else:
        try:
            result = datetime.fromisoformat(value)
        except ValueError as exc:
            raise SessmarkError("--since/--until requires today, 1d/24h/30m, or ISO 8601") from exc
        if result.tzinfo is None:
            result = result.astimezone()
    return result.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Locator:
    harness: str
    session_id: str | None = None
    transcript_path: str | None = None
    resume_cmd: tuple[str, ...] = ()

    def __post_init__(self):
        nonempty(self.harness, "harness", 128)
        if self.harness != self.harness.lower():
            raise SessmarkError("harness must be lowercase")
        if self.session_id is not None:
            nonempty(self.session_id, "session_id", 512)
            if self.session_id.startswith("-"):
                raise SessmarkError("session_id cannot start with '-' (CLI option ambiguity)")
        if self.transcript_path is not None:
            nonempty(self.transcript_path, "transcript_path")
            if not Path(self.transcript_path).is_absolute():
                raise SessmarkError("transcript_path must be absolute")
        if isinstance(self.resume_cmd, str):
            raise SessmarkError("resume_cmd must be argv, never a shell command string")
        for arg in self.resume_cmd:
            nonempty(arg, "resume argument")

    def as_dict(self):
        return {
            "kind": "native" if self.session_id else "pending",
            **asdict(self),
            "resume_cmd": list(self.resume_cmd),
        }


@dataclass(frozen=True)
class Binding:
    """Opaque host address + incarnation. Only adapters interpret metadata."""

    source: str
    key: str
    generation: str
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("source", "key", "generation"):
            nonempty(getattr(self, name), name)
