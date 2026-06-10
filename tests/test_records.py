from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pdocs.records import RecordError, add_record, list_records
from pdocs.view import build_view, build_view_from_head


class CopyCipher:
    def seal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def unseal(self, source: Path, destination: Path) -> None:
        shutil.copy2(source, destination)


def test_replaceable_record_updates_stable_path(tmp_path: Path):
    vault = tmp_path / "vault"
    source = tmp_path / "permit.pdf"
    source.write_bytes(b"first")
    cipher = CopyCipher()

    first = add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="identity/current-permit",
        title="Residence permit",
        domain="identity-residence",
        owner="self",
        lifecycle="replaceable",
    )
    source.write_bytes(b"second")
    second = add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="identity/current-permit",
        title="Residence permit",
        domain="identity-residence",
        owner="self",
        lifecycle="replaceable",
    )

    assert first == second
    records = list_records(vault, cipher)
    assert len(records) == 1
    assert records[0]["content"]["filename"] == "permit.pdf"


def test_event_record_cannot_be_overwritten(tmp_path: Path):
    source = tmp_path / "decision.eml"
    source.write_bytes(b"message")
    kwargs = dict(
        vault=tmp_path / "vault",
        cipher=CopyCipher(),
        source_path=source,
        record_id="cases/example/2026-06-10-decision",
        title="Decision",
        domain="legal-cases",
        owner="self",
        lifecycle="event",
    )
    add_record(**kwargs)
    with pytest.raises(RecordError):
        add_record(**kwargs)
    with pytest.raises(RecordError):
        add_record(**{**kwargs, "lifecycle": "replaceable"})


def test_build_view_materializes_latest_records(tmp_path: Path):
    vault = tmp_path / "vault"
    readable = tmp_path / "readable"
    source = tmp_path / "contract.txt"
    source.write_text("terms", encoding="utf-8")
    cipher = CopyCipher()
    add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="employment/example/contract",
        title="Contract",
        domain="employment",
        owner="self",
        lifecycle="replaceable",
    )

    assert build_view(vault, readable, cipher) == 1
    assert (readable / "employment/example/contract/contract.txt").read_text(
        encoding="utf-8"
    ) == "terms"


def test_view_from_head_ignores_uncommitted_records(tmp_path: Path):
    vault = tmp_path / "vault"
    readable = tmp_path / "readable"
    source = tmp_path / "contract.txt"
    source.write_text("committed", encoding="utf-8")
    cipher = CopyCipher()
    record = dict(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="employment/example/contract",
        title="Contract",
        domain="employment",
        owner="self",
        lifecycle="replaceable",
    )
    add_record(**record)
    subprocess.run(["git", "init", "-q"], cwd=vault, check=True)
    subprocess.run(["git", "add", "records"], cwd=vault, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "Add record",
        ],
        cwd=vault,
        check=True,
    )

    source.write_text("uncommitted", encoding="utf-8")
    add_record(**record)

    assert build_view_from_head(vault, readable, cipher) == 1
    assert (readable / "employment/example/contract/contract.txt").read_text(
        encoding="utf-8"
    ) == "committed"
