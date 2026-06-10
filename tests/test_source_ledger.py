from __future__ import annotations

import shutil
from pathlib import Path

from pdocs.source_ledger import SourceLedger


class XorCipher:
    def seal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            bytes(value ^ 0xA5 for value in source.read_bytes())
        )

    def unseal(self, source: Path, destination: Path) -> None:
        destination.write_bytes(
            bytes(value ^ 0xA5 for value in source.read_bytes())
        )


def _complete(ledger: SourceLedger, key: str) -> Path:
    return ledger.complete(
        key=key,
        kind="folder",
        profile="iphone",
        identity={"root": "/exchange/Inbox"},
        run={
            "run_id": "run-1",
            "started_at": "2026-06-10T10:00:00+00:00",
            "completed_at": "2026-06-10T10:01:00+00:00",
            "last_completed_source_time": "2026-06-10T10:00:00+00:00",
            "items_seen": 1,
            "items_exported": 1,
            "items_skipped_duplicate": 0,
        },
        items=[
            {
                "source_item_id": "scan.pdf",
                "source_ref": "scan.pdf",
                "content_sha256": "abc123",
                "source_time": "2026-06-10T09:00:00+00:00",
                "exported": True,
            }
        ],
    )


def test_encrypted_ledger_replays_across_copied_vault(tmp_path: Path):
    cipher = XorCipher()
    first_vault = tmp_path / "first"
    key = "folder:iphone:example"
    event = _complete(SourceLedger(first_vault, cipher), key)

    assert b"scan.pdf" not in event.read_bytes()

    second_vault = tmp_path / "second"
    shutil.copytree(first_vault, second_vault)
    state = SourceLedger(second_vault, cipher).state(key)

    assert state is not None
    assert state.last_successful_run_at == "2026-06-10T10:01:00+00:00"
    assert state.seen_items[0]["content_sha256"] == "abc123"


def test_reset_event_clears_effective_state_without_deleting_history(tmp_path: Path):
    cipher = XorCipher()
    ledger = SourceLedger(tmp_path / "vault", cipher)
    key = "folder:iphone:example"
    _complete(ledger, key)
    ledger.reset(key, kind="folder", profile="iphone")

    assert ledger.state(key) is None
    assert len(list(ledger.events.glob("*.pdoc"))) == 2


def test_rebuild_local_index_is_derived_from_encrypted_events(tmp_path: Path):
    cipher = XorCipher()
    ledger = SourceLedger(tmp_path / "vault", cipher)
    _complete(ledger, "folder:iphone:example")

    index = ledger.rebuild_local_index(tmp_path / "local-state")

    assert index.is_file()
    assert "folder:iphone:example" in index.read_text(encoding="utf-8")
    assert index.stat().st_mode & 0o777 == 0o600
