import json
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sessmark import Binding, Locator, SessmarkError, Store
from sessmark.model import since_time


def binding(generation="term-1"):
    return Binding("example-host", "pane-1", generation)


def test_native_identity_ignores_cwd_and_path(tmp_path):
    with Store(tmp_path / "db") as store:
        one = store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), tags=["keep"])
        two = store.mark(
            locator=Locator("grok", "a", str(tmp_path / "moved")),
            cwd=str(tmp_path / "other"),
            note="中文路径与批注",
        )
        assert one["id"] == two["id"]
        assert two["tags"] == ["keep"]
        assert store.get(one["id"])[1][0]["text"] == "中文路径与批注"
        three = store.mark(locator=Locator("codex", "a"), cwd=str(tmp_path), tags=["keep"])
        assert three["id"] != one["id"]


def test_rebind_merge_aliases_and_annotation_time(tmp_path):
    times = iter([f"2026-09-06T00:00:{i:02d}.000000+00:00" for i in range(30)])
    with Store(tmp_path / "db", clock=lambda: next(times)) as store:
        pending = store.mark(
            locator=Locator("grok"),
            cwd=str(tmp_path),
            binding=binding(),
            tags=["review:problem"],
            note="before binding",
        )
        native = store.mark(
            locator=Locator("grok", "a"),
            cwd=str(tmp_path),
            tags=["prio:p0"],
            note="known outside the host",
        )
        id = store.observe(Locator("grok", "a"), str(tmp_path), binding())
        assert id == pending["id"]
        assert len(store.list()) == 1
        session, notes = store.get(native["id"])
        assert session["id"] == id
        assert session["updated_at"] == native["updated_at"]
        assert session["tags"] == ["prio:p0", "review:problem"]
        assert len(notes) == 2
        assert store.observe(Locator("grok", "a"), str(tmp_path), binding()) == id
        store.mark(id=native["id"], note="old ID remains writable")
        assert len(store.get(id)[1]) == 3


def test_native_first_merge_and_multiple_aliases(tmp_path):
    with Store(tmp_path / "db") as store:
        native = store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), tags=["keep"])
        for i in range(3):
            b = Binding("host", f"pane-{i}", "term")
            p = store.mark(locator=Locator("grok"), cwd=str(tmp_path), binding=b, note=str(i))
            assert store.observe(Locator("grok", "a"), str(tmp_path), b) == native["id"]
            assert store.get(p["id"])[0]["id"] == native["id"]
        assert len(store.get(native["id"])[1]) == 3
        assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_pane_reuse_does_not_merge_conversations(tmp_path):
    with Store(tmp_path / "db") as store:
        one = store.mark(
            locator=Locator("grok", "a"), cwd=str(tmp_path), binding=binding(), tags=["keep"]
        )
        two = store.mark(
            locator=Locator("grok", "b"), cwd=str(tmp_path), binding=binding(), note="new"
        )
        assert one["id"] != two["id"]
        assert two["tags"] == []
        three = store.mark(
            locator=Locator("grok"), cwd=str(tmp_path), binding=binding("term-2"), tags=["prio:p0"]
        )
        assert store.observe(Locator("grok", "c"), str(tmp_path), binding()) is None
        assert store.get(three["id"])[0]["locator"]["session_id"] is None


def test_path_only_reference_is_not_global_identity(tmp_path):
    with Store(tmp_path / "db") as store:
        loc = Locator("pi", transcript_path=str(tmp_path / "pi.jsonl"))
        one = store.mark(locator=loc, cwd=str(tmp_path), binding=binding(), tags=["keep"])
        two = store.mark(
            locator=loc, cwd=str(tmp_path), binding=Binding("host", "other", "1"), tags=["keep"]
        )
        assert one["id"] != two["id"]


def test_unknown_tags_and_blank_notes_leave_no_rows(tmp_path):
    with Store(tmp_path / "db") as store:
        for fields in ({"tags": ["keep", "typo"]}, {"note": " "}, {"note": "bad\x1b[2J"}):
            with pytest.raises(SessmarkError):
                store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), **fields)
        assert store.list() == []
        with pytest.raises(SessmarkError, match="Unknown tags"):
            store.list(["typo"])


def test_transaction_rolls_back_rebind_and_merge(tmp_path):
    with Store(tmp_path / "db") as store:
        p = store.mark(
            locator=Locator("grok"), cwd=str(tmp_path), binding=binding(), note="pending"
        )
        n = store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), note="native")
        store.db.execute(
            "CREATE TRIGGER fail_update BEFORE UPDATE ON bindings BEGIN SELECT RAISE(ABORT, 'crash'); END"
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.observe(Locator("grok", "a"), str(tmp_path), binding())
        assert len(store.list()) == 2
        assert store.get(p["id"])[1][0]["text"] == "pending"
        assert store.get(n["id"])[1][0]["text"] == "native"


def test_context_routes_partial_and_no_transcript_read(tmp_path):
    path = tmp_path / "never-open.jsonl"
    with Store(tmp_path / "db") as store:
        row = store.mark(
            locator=Locator("grok", "a", str(path)),
            cwd=str(tmp_path),
            tags=["review:problem", "harvest:doc"],
            note="notes are data",
        )
        with pytest.raises(SessmarkError, match="Multiple prompt routes"):
            store.context(row["id"])
        ctx = store.context(row["id"], tag="harvest:doc")
        assert ctx["schema"] == "sessmark.context.v1"
        assert ctx["prompt"]["template_id"] == "harvest-doc"
        assert ctx["partial"] is True
        assert not path.exists()
        assert set(ctx) == {"schema", "session", "notes", "prompt", "partial", "how_to_read"}
        assert ctx["session"]["locator"]["transcript_path"] == str(path)
        json.dumps(ctx, ensure_ascii=False)


def test_time_boundaries_and_repeated_tag_is_a_new_mark(tmp_path):
    now = datetime(2026, 9, 6, 12, tzinfo=UTC)
    assert since_time("1d", now) == "2026-09-05T12:00:00.000000+00:00"
    local_midnight = datetime.combine(now.astimezone().date(), datetime.min.time()).astimezone()
    assert since_time("today", now) == local_midnight.astimezone(UTC).isoformat(
        timespec="microseconds"
    )
    assert since_time("2026-09-06T08:00:00+08:00", now) == "2026-09-06T00:00:00.000000+00:00"
    clock = ["2026-09-06T00:00:00.000000+00:00"]
    with Store(tmp_path / "db", clock=lambda: clock[0]) as store:
        row = store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), tags=["keep"])
        assert len(store.list(since=clock[0])) == 1
        assert store.list(until=clock[0]) == []
        clock[0] = "2026-09-07T00:00:00.000000+00:00"
        store.mark(id=row["id"], tags=["keep"])
        assert len(store.list(since=clock[0])) == 1
        assert store.list()[0]["tags"] == ["keep"]


def concurrent_writer(path, index):
    with Store(path) as store:
        return store.mark(
            locator=Locator("grok", "same"),
            cwd=str(Path(path).parent),
            tags=["keep"],
            note=f"writer-{index}",
        )["id"]


def test_concurrent_processes_create_one_identity_and_keep_all_notes(tmp_path):
    with ProcessPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(concurrent_writer, [str(tmp_path / "db")] * 12, range(12)))
    assert len(set(ids)) == 1
    with Store(tmp_path / "db") as store:
        assert len(store.get(ids[0])[1]) == 12


def test_manual_bind_recovers_closed_host_and_preserves_time(tmp_path):
    with Store(tmp_path / "db") as store:
        pending = store.mark(
            locator=Locator("grok"), cwd=str(tmp_path), binding=binding(), tags=["keep"]
        )
        native = store.mark(locator=Locator("grok", "a"), cwd=str(tmp_path), note="native")
        row = store.bind(pending["id"], Locator("grok", "a"))
        assert row["id"] == pending["id"]
        assert row["updated_at"] == native["updated_at"]
        assert store.get(native["id"])[0]["id"] == row["id"]
        with pytest.raises(SessmarkError, match="established"):
            store.bind(row["id"], Locator("grok", "other"))
