from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pdocs.records import RecordError, add_record, list_records, organize_record
from pdocs.view import ViewError, build_view, build_view_from_head


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
        view_name="Residence permit",
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
        view_name="Residence permit",
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
        view_name="Decision",
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
        view_name="Contract",
        domain="employment",
        owner="self",
        lifecycle="replaceable",
    )

    assert build_view(vault, readable, cipher) == 1
    assert (readable / "Employment/Contract.txt").read_text() == "terms"
    metadata = (readable / ".metadata/Employment/Contract.json").read_text(
        encoding="utf-8"
    )
    assert '"issued_at": null' in metadata
    index = json.loads((readable / "INDEX.json").read_text())
    assert index[0]["view"]["document"] == "Employment/Contract.txt"


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
        view_name="Contract",
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
    assert (readable / "Employment/Contract.txt").read_text() == "committed"


def test_view_uses_dates_only_to_disambiguate_equal_titles(tmp_path: Path):
    vault = tmp_path / "vault"
    cipher = CopyCipher()
    for issued_at in ("2025-01-01", "2025-02-01"):
        source = tmp_path / f"{issued_at}.pdf"
        source.write_bytes(issued_at.encode())
        add_record(
            vault=vault,
            cipher=cipher,
            source_path=source,
            record_id=f"employment/example/payslip/{issued_at}",
            title="Example employer payslip",
            view_name=f"Example employer payslip - {issued_at}",
            domain="employment",
            owner="self",
            lifecycle="event",
            issued_at=issued_at,
        )

    readable = tmp_path / "readable"
    assert build_view(vault, readable, cipher) == 2
    assert (readable / "Employment/Example employer payslip - 2025-01-01.pdf").exists()
    assert (readable / "Employment/Example employer payslip - 2025-02-01.pdf").exists()


def test_record_organization_persists_readable_overrides(tmp_path: Path):
    vault = tmp_path / "vault"
    cipher = CopyCipher()
    source = tmp_path / "opaque-name.pdf"
    source.write_bytes(b"original")
    add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="employment/example/contract",
        title="Employment contract",
        view_name="Employment contract",
        domain="employment",
        owner="self",
        lifecycle="event",
        issued_at="2026-03-30",
    )

    metadata = organize_record(
        vault=vault,
        cipher=cipher,
        record_id="employment/example/contract",
        name="Example employment agreement",
        folder="Work/Example employer",
    )
    assert metadata["title"] == "Employment contract"
    assert metadata["issued_at"] == "2026-03-30"
    assert metadata["presentation"] == {
        "name": "Example employment agreement",
        "folder": "Work/Example employer",
    }

    readable = tmp_path / "readable"
    build_view(vault, readable, cipher)
    assert (
        readable / "Work/Example employer/Example employment agreement.pdf"
    ).read_bytes() == b"original"


def test_view_rejects_duplicate_agent_names(tmp_path: Path):
    vault = tmp_path / "vault"
    cipher = CopyCipher()
    for index in (1, 2):
        source = tmp_path / f"document-{index}.pdf"
        source.write_bytes(str(index).encode())
        add_record(
            vault=vault,
            cipher=cipher,
            source_path=source,
            record_id=f"employment/example/document-{index}",
            title=f"Document {index}",
            view_name="Example document",
            domain="employment",
            owner="self",
            lifecycle="event",
        )

    with pytest.raises(ViewError, match="Duplicate readable filename"):
        build_view(vault, tmp_path / "readable", cipher)
