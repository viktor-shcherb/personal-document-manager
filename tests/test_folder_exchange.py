from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pdocs.folder_exchange import (
    FolderExchangeError,
    discover_folder,
    export_view_to_folder,
)
from pdocs.records import add_record


class CopyCipher:
    def seal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def unseal(self, source: Path, destination: Path) -> None:
        shutil.copy2(source, destination)


def test_discover_folder_filters_hidden_partial_and_unsupported_files(tmp_path: Path):
    source = tmp_path / "Inbox"
    source.mkdir()
    (source / "document.pdf").write_bytes(b"pdf")
    (source / ".hidden.pdf").write_bytes(b"hidden")
    (source / "partial.pdf.part").write_bytes(b"partial")
    (source / "notes.txt").write_bytes(b"text")
    (source / "empty.jpg").write_bytes(b"")

    candidates = discover_folder(source, extensions=(".pdf", ".jpg"))

    assert [item.relative_path for item in candidates] == ["document.pdf"]


def test_view_export_is_idempotent_and_prunes_only_managed_files(tmp_path: Path):
    vault = tmp_path / "vault"
    destination = tmp_path / "exchange" / "Views"
    source = tmp_path / "document.txt"
    source.write_text("current", encoding="utf-8")
    cipher = CopyCipher()
    add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="identity/document",
        title="Document",
        domain="identity",
        owner="self",
        lifecycle="replaceable",
    )
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=vault, check=True)
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

    first = export_view_to_folder(
        vault=vault,
        destination=destination,
        cipher=cipher,
    )
    unrelated = destination / "user-note.txt"
    unrelated.write_text("keep", encoding="utf-8")
    second = export_view_to_folder(
        vault=vault,
        destination=destination,
        cipher=cipher,
    )

    assert first["changed"] > 0
    assert second["changed"] == 0
    assert (destination / "identity/document/document.txt").read_text() == "current"
    metadata = json.loads((destination / "identity/document/metadata.json").read_text())
    assert metadata["id"] == "identity/document"

    subprocess.run(["git", "rm", "-q", "-r", "records"], cwd=vault, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "Remove record",
        ],
        cwd=vault,
        check=True,
    )
    export_view_to_folder(
        vault=vault,
        destination=destination,
        cipher=cipher,
        prune=False,
    )
    assert (destination / "identity/document/document.txt").exists()

    result = export_view_to_folder(
        vault=vault,
        destination=destination,
        cipher=cipher,
        prune=True,
    )
    assert result["pruned"] > 0
    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_view_export_rejects_symlink_redirect_outside_destination(tmp_path: Path):
    vault = tmp_path / "vault"
    destination = tmp_path / "exchange"
    outside = tmp_path / "outside"
    source = tmp_path / "document.txt"
    source.write_text("current", encoding="utf-8")
    outside.mkdir()
    cipher = CopyCipher()
    add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="identity/document",
        title="Document",
        domain="identity",
        owner="self",
        lifecycle="replaceable",
    )
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=vault, check=True)
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
    destination.mkdir()
    (destination / "identity").symlink_to(outside, target_is_directory=True)

    with pytest.raises(FolderExchangeError, match="escapes destination"):
        export_view_to_folder(
            vault=vault,
            destination=destination,
            cipher=cipher,
        )

    assert not list(outside.rglob("*"))
