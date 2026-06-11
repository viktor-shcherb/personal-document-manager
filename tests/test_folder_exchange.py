from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pdocs.config import ViewTargetConfig
from pdocs.folder_exchange import (
    FolderExchangeError,
    discover_folder,
    export_view_to_folder,
    refresh_views,
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
        view_name="Document",
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
    assert (destination / "Identity/Document.txt").read_text() == "current"
    metadata = json.loads(
        (destination / ".metadata/Identity/Document.json").read_text()
    )
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
    assert (destination / "Identity/Document.txt").exists()

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
        view_name="Document",
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
    (destination / "Identity").symlink_to(outside, target_is_directory=True)

    with pytest.raises(FolderExchangeError, match="escapes destination"):
        export_view_to_folder(
            vault=vault,
            destination=destination,
            cipher=cipher,
        )

    assert not list(outside.rglob("*"))


def test_refresh_views_materializes_one_commit_to_all_targets(tmp_path: Path):
    vault = tmp_path / "vault"
    source = tmp_path / "document.txt"
    source.write_text("current", encoding="utf-8")
    cipher = CopyCipher()
    add_record(
        vault=vault,
        cipher=cipher,
        source_path=source,
        record_id="identity/document",
        title="Document",
        view_name="Document",
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
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=vault,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    targets = {
        "local": ViewTargetConfig(
            name="local",
            path=tmp_path / "local-view",
            prune=True,
        ),
        "icloud": ViewTargetConfig(
            name="icloud",
            path=tmp_path / "icloud-view",
            prune=True,
        ),
    }

    first = refresh_views(vault=vault, targets=targets, cipher=cipher)
    second = refresh_views(vault=vault, targets=targets, cipher=cipher)

    assert {item["name"] for item in first} == {"local", "icloud"}
    assert all(item["commit"] == commit for item in first)
    assert all(not item["skipped"] for item in first)
    assert all(item["skipped"] for item in second)
    for target in targets.values():
        manifest = json.loads((target.path / ".pdocs-folder-export.json").read_text())
        assert manifest["schema"] == 2
        assert manifest["commit"] == commit
        assert (target.path / "Identity/Document.txt").read_text() == "current"

    missing = targets["local"].path / "Identity/Document.txt"
    missing.unlink()
    repaired = refresh_views(vault=vault, targets=targets, cipher=cipher)
    by_name = {item["name"]: item for item in repaired}
    assert by_name["local"]["skipped"] is False
    assert by_name["icloud"]["skipped"] is True
    assert missing.read_text() == "current"


def test_refresh_views_rejects_overlapping_targets(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=vault, check=True)
    (vault / "README").write_text("vault")
    subprocess.run(["git", "add", "README"], cwd=vault, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "Initialize",
        ],
        cwd=vault,
        check=True,
    )
    targets = {
        "parent": ViewTargetConfig(
            name="parent",
            path=tmp_path / "views",
            prune=True,
        ),
        "child": ViewTargetConfig(
            name="child",
            path=tmp_path / "views/child",
            prune=True,
        ),
    }

    with pytest.raises(FolderExchangeError, match="must not overlap"):
        refresh_views(vault=vault, targets=targets, cipher=CopyCipher())
