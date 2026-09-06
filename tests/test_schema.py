import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from sessmark import Binding, Locator, Store


def test_output_matches_published_json_schemas(tmp_path):
    root = Path(__file__).resolve().parents[1] / "schemas"
    session = json.loads((root / "session.v1.schema.json").read_text("utf-8"))
    context = json.loads((root / "context.v1.schema.json").read_text("utf-8"))
    Draft202012Validator.check_schema(session)
    Draft202012Validator.check_schema(context)
    registry = Registry().with_resource("session.v1.schema.json", Resource.from_contents(session))
    validator = Draft202012Validator(context, registry=registry, format_checker=FormatChecker())
    with Store(tmp_path / "db") as store:
        for loc, binding in [
            (Locator("grok", "abc"), None),
            (Locator("grok"), Binding("host", "pane", "terminal")),
        ]:
            row = store.mark(
                locator=loc,
                cwd=str(tmp_path),
                binding=binding,
                tags=["review:problem"],
                note="中文" * 170,
            )
            assert len(row["notes_preview"]) == 160
            validator.validate(store.context(row["id"]))
