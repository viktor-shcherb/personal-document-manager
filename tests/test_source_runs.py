from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from pdocs.config import (
    FolderSourceProfile,
    GmailSourceProfile,
    SourcesConfig,
    ViewTargetConfig,
    ViewsConfig,
)
from pdocs.interfaces import SourceCandidate
from pdocs.source_ledger import SourceLedger, SourceLedgerError
from pdocs.source_runs import run_folder_source, run_gmail_source


class CopyCipher:
    def seal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def unseal(self, source: Path, destination: Path) -> None:
        shutil.copy2(source, destination)


def _config(tmp_path: Path):
    exchange = tmp_path / "exchange"
    return SimpleNamespace(
        paths=SimpleNamespace(
            vault=tmp_path / "vault",
            inbox=tmp_path / "local-inbox",
            state=tmp_path / "local-state",
        ),
        gmail=SimpleNamespace(account="user@example.com"),
        sources=SourcesConfig(
            gmail={
                "documents": GmailSourceProfile(
                    name="documents",
                    query="has:attachment",
                    initial_window="30d",
                    overlap_window="24h",
                )
            },
            folder={
                "iphone": FolderSourceProfile(
                    name="iphone",
                    root=exchange,
                    inbox="Inbox",
                    extensions=(".pdf", ".jpg"),
                )
            },
        ),
        views=ViewsConfig(
            refresh_interval_seconds=300,
            targets={
                "local": ViewTargetConfig(
                    name="local",
                    path=tmp_path / "readable",
                    prune=True,
                )
            },
        ),
    )


class FakeGmail:
    def __init__(self, inbox: Path, candidates: list[SourceCandidate]):
        self.inbox = inbox
        self.candidates = candidates
        self.queries = []

    def search(self, query: str, limit: int):
        self.queries.append(query)
        return self.candidates[:limit]

    def export(self, message_id: str) -> Path:
        destination = self.inbox / "email" / message_id
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "message.eml").write_bytes(
            f"Message-ID: {message_id}\n\ncontent {message_id}".encode()
        )
        (destination / "source.json").write_text(
            json.dumps({"message_id": message_id}) + "\n",
            encoding="utf-8",
        )
        return destination


def _candidate(message_id: str, source_time: str) -> SourceCandidate:
    return SourceCandidate(
        reference=message_id,
        thread_reference=f"thread-{message_id}",
        received_at=source_time,
        source_time=source_time,
        sender="sender@example.com",
        subject="Document",
        has_attachments=True,
    )


def test_gmail_runs_incrementally_with_overlap_and_deduplication(tmp_path: Path):
    config = _config(tmp_path)
    cipher = CopyCipher()
    first_gmail = FakeGmail(
        config.paths.inbox,
        [_candidate("message-1", "2026-06-10T09:00:00+00:00")],
    )
    first = run_gmail_source(
        config=config,
        cipher=cipher,
        gmail=first_gmail,
        profile_name="documents",
        now=datetime(2026, 6, 10, 10, tzinfo=UTC),
    )

    second_gmail = FakeGmail(
        config.paths.inbox,
        [
            _candidate("message-1", "2026-06-10T09:00:00+00:00"),
            _candidate("message-2", "2026-06-17T09:00:00+00:00"),
        ],
    )
    second = run_gmail_source(
        config=config,
        cipher=cipher,
        gmail=second_gmail,
        profile_name="documents",
        now=datetime(2026, 6, 17, 10, tzinfo=UTC),
    )

    assert "after:2026/06/09" in second_gmail.queries[0]
    assert first.items_exported == 1
    assert second.items_exported == 1
    assert second.items_skipped_duplicate == 1
    state = SourceLedger(config.paths.vault, cipher).state(first.source_key)
    assert state is not None
    assert {item["source_item_id"] for item in state.seen_items} == {
        "message-1",
        "message-2",
    }


def test_failed_gmail_run_does_not_advance_shared_ledger(tmp_path: Path):
    config = _config(tmp_path)
    cipher = CopyCipher()

    class FailingGmail:
        def search(self, query: str, limit: int):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        run_gmail_source(
            config=config,
            cipher=cipher,
            gmail=FailingGmail(),
            profile_name="documents",
            now=datetime(2026, 6, 10, 10, tzinfo=UTC),
        )

    assert not list(
        (config.paths.vault / ".pdocs/state/source-ledger/events").glob("*.pdoc")
    )
    assert list((config.paths.state / "source-runs/failures").glob("*.json"))


def test_folder_run_skips_seen_files_and_surfaces_changed_content(tmp_path: Path):
    config = _config(tmp_path)
    cipher = CopyCipher()
    inbox = config.sources.folder["iphone"].inbox_path()
    inbox.mkdir(parents=True)
    document = inbox / "scan.pdf"
    document.write_bytes(b"issue 1")

    first = run_folder_source(
        config=config,
        cipher=cipher,
        profile_name="iphone",
        now=datetime(2026, 6, 10, 10, tzinfo=UTC),
    )
    second = run_folder_source(
        config=config,
        cipher=cipher,
        profile_name="iphone",
        now=datetime(2026, 6, 11, 10, tzinfo=UTC),
    )
    document.write_bytes(b"issue 2")
    third = run_folder_source(
        config=config,
        cipher=cipher,
        profile_name="iphone",
        now=datetime(2026, 6, 12, 10, tzinfo=UTC),
    )

    assert first.items_exported == 1
    assert second.items_exported == 0
    assert second.items_skipped_duplicate == 1
    assert third.items_exported == 1
    assert third.batch is not None
    assert (third.batch / "scan.pdf").read_bytes() == b"issue 2"


def test_folder_ledger_replay_prevents_duplicate_on_second_device(tmp_path: Path):
    first = _config(tmp_path / "first-device")
    cipher = CopyCipher()
    source = first.sources.folder["iphone"].inbox_path()
    source.mkdir(parents=True)
    (source / "scan.pdf").write_bytes(b"shared")
    initial = run_folder_source(
        config=first,
        cipher=cipher,
        profile_name="iphone",
    )

    second = _config(tmp_path / "second-device")
    second.sources.folder["iphone"].inbox_path().mkdir(parents=True)
    (second.sources.folder["iphone"].inbox_path() / "scan.pdf").write_bytes(b"shared")
    shutil.copytree(first.paths.vault, second.paths.vault)
    repeated = run_folder_source(
        config=second,
        cipher=cipher,
        profile_name="iphone",
    )

    assert initial.items_exported == 1
    assert repeated.items_exported == 0
    assert repeated.items_skipped_duplicate == 1


def test_folder_reset_makes_content_eligible_for_import_again(tmp_path: Path):
    config = _config(tmp_path)
    cipher = CopyCipher()
    source = config.sources.folder["iphone"].inbox_path()
    source.mkdir(parents=True)
    (source / "scan.pdf").write_bytes(b"shared")
    initial = run_folder_source(
        config=config,
        cipher=cipher,
        profile_name="iphone",
    )
    ledger = SourceLedger(config.paths.vault, cipher)
    ledger.reset(initial.source_key, kind="folder", profile="iphone")

    repeated = run_folder_source(
        config=config,
        cipher=cipher,
        profile_name="iphone",
    )

    assert repeated.items_exported == 1


def test_full_gmail_run_removes_incremental_start_but_retains_dedupe(tmp_path: Path):
    config = _config(tmp_path)
    cipher = CopyCipher()
    candidate = _candidate("message-1", "2026-06-10T09:00:00+00:00")
    run_gmail_source(
        config=config,
        cipher=cipher,
        gmail=FakeGmail(config.paths.inbox, [candidate]),
        profile_name="documents",
        now=datetime(2026, 6, 10, 10, tzinfo=UTC),
    )
    gmail = FakeGmail(config.paths.inbox, [candidate])

    result = run_gmail_source(
        config=config,
        cipher=cipher,
        gmail=gmail,
        profile_name="documents",
        full=True,
        now=datetime(2026, 6, 17, 10, tzinfo=UTC),
    )

    assert "after:" not in gmail.queries[0]
    assert result.items_exported == 0
    assert result.items_skipped_duplicate == 1


def test_folder_source_rejects_overlap_with_local_work_areas(tmp_path: Path):
    config = _config(tmp_path)
    config.paths.inbox.mkdir(parents=True)

    with pytest.raises(SourceLedgerError, match="local inbox"):
        run_folder_source(
            config=config,
            cipher=CopyCipher(),
            profile_name="ad-hoc",
            folder_override=config.paths.inbox,
        )
