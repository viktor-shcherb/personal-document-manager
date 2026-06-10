from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import FolderSourceProfile
from .interfaces import Cipher
from .records import sha256
from .view import MARKER, build_view_from_head


EXPORT_MANIFEST = ".pdocs-folder-export.json"
TEMPORARY_SUFFIXES = (".tmp", ".part", ".partial", ".crdownload", ".download")
UF_OFFLINE = getattr(stat, "UF_OFFLINE", 0x40000000)


class FolderExchangeError(RuntimeError):
    pass


@dataclass(frozen=True)
class FolderCandidate:
    path: Path
    relative_path: str
    size: int
    modified_at: str
    content_sha256: str


def resolve_ingest_folder(
    profile: FolderSourceProfile | None,
    override: Path | None,
) -> Path:
    if override:
        return override.expanduser().resolve()
    if not profile:
        raise FolderExchangeError(
            "Folder source profile is missing; configure [sources.folder.PROFILE] "
            "or pass --folder"
        )
    return profile.inbox_path()


def resolve_views_folder(
    profile: FolderSourceProfile | None,
    override: Path | None,
) -> Path:
    if override:
        return override.expanduser().resolve()
    if not profile:
        raise FolderExchangeError(
            "Folder source profile is missing; configure [sources.folder.PROFILE] "
            "or pass --folder"
        )
    return profile.views_path()


def _is_hidden_or_temporary(relative: Path) -> bool:
    if any(part.startswith(".") for part in relative.parts):
        return True
    lower_name = relative.name.lower()
    return lower_name.endswith("~") or lower_name.endswith(TEMPORARY_SUFFIXES)


def discover_folder(
    folder: Path,
    *,
    extensions: tuple[str, ...],
) -> list[FolderCandidate]:
    if not folder.is_dir():
        raise FolderExchangeError(f"Folder source does not exist: {folder}")
    candidates = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if _is_hidden_or_temporary(relative):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        details = path.stat()
        if getattr(details, "st_flags", 0) & UF_OFFLINE:
            continue
        if details.st_size <= 0:
            continue
        candidates.append(
            FolderCandidate(
                path=path,
                relative_path=relative.as_posix(),
                size=details.st_size,
                modified_at=datetime.fromtimestamp(details.st_mtime, tz=UTC)
                .replace(microsecond=0)
                .isoformat(),
                content_sha256=sha256(path),
            )
        )
    return candidates


def stage_folder_candidates(
    candidates: list[FolderCandidate],
    *,
    inbox: Path,
    profile: str,
    run_id: str,
    source_key: str,
) -> tuple[Path | None, list[dict]]:
    if not candidates:
        return None, []
    batch = inbox / "folder" / profile / run_id
    if batch.exists():
        raise FolderExchangeError(f"Folder intake batch already exists: {batch}")
    staged_items = []
    try:
        for candidate in candidates:
            destination = batch / candidate.relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.tmp")
            shutil.copy2(candidate.path, temporary)
            if sha256(temporary) != candidate.content_sha256:
                raise FolderExchangeError(
                    f"Copied folder candidate failed checksum verification: "
                    f"{candidate.path}"
                )
            temporary.replace(destination)
            staged_items.append(
                {
                    "source_kind": "folder",
                    "source_profile": profile,
                    "source_key": source_key,
                    "source_ref": candidate.relative_path,
                    "content_sha256": candidate.content_sha256,
                    "size": candidate.size,
                    "modified_at": candidate.modified_at,
                    "staged_path": str(destination),
                }
            )
        (batch / "manifest.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "source_kind": "folder",
                    "source_profile": profile,
                    "source_key": source_key,
                    "run_id": run_id,
                    "items": staged_items,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(batch, ignore_errors=True)
        raise
    return batch, staged_items


def _managed_files(root: Path) -> set[str]:
    manifest = root / EXPORT_MANIFEST
    if not manifest.is_file():
        return set()
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise FolderExchangeError(
            f"Invalid folder export manifest: {manifest}"
        ) from error
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise FolderExchangeError(f"Unsupported folder export manifest: {manifest}")
    managed = set()
    for value in data.get("files", ()):
        if not isinstance(value, str):
            raise FolderExchangeError(
                f"Unsafe managed path in folder export manifest: {value!r}"
            )
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise FolderExchangeError(
                f"Unsafe managed path in folder export manifest: {value!r}"
            )
        managed.add(path.as_posix())
    return managed


def _copy_if_changed(source: Path, destination: Path) -> bool:
    if (
        destination.is_file()
        and destination.stat().st_size == source.stat().st_size
        and sha256(destination) == sha256(source)
    ):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _managed_destination(root: Path, relative: str) -> Path:
    destination = root / relative
    resolved = destination.resolve()
    if resolved == root or root not in resolved.parents:
        raise FolderExchangeError(
            f"Managed export path escapes destination through a symlink: {relative!r}"
        )
    return destination


def export_view_to_folder(
    *,
    vault: Path,
    destination: Path,
    cipher: Cipher,
    prune: bool = False,
) -> dict:
    resolved_vault = vault.resolve()
    resolved_destination = destination.expanduser().resolve()
    if (
        resolved_destination == resolved_vault
        or resolved_vault in resolved_destination.parents
    ):
        raise FolderExchangeError("Readable export folder must be outside the vault")

    destination = resolved_destination
    destination.mkdir(parents=True, exist_ok=True)
    previous = _managed_files(destination)
    with tempfile.TemporaryDirectory() as temporary_dir:
        generated = Path(temporary_dir) / "view"
        count = build_view_from_head(vault, generated, cipher)
        current = {
            path.relative_to(generated).as_posix()
            for path in generated.rglob("*")
            if path.is_file() and path.name != MARKER
        }
        changed = 0
        for relative in sorted(current):
            managed_destination = _managed_destination(destination, relative)
            if _copy_if_changed(generated / relative, managed_destination):
                changed += 1

    pruned = 0
    if prune:
        for relative in sorted(previous - current):
            path = _managed_destination(destination, relative)
            if path.is_file():
                path.unlink()
                pruned += 1
        for directory in sorted(destination.rglob("*"), reverse=True):
            if (
                not directory.is_symlink()
                and directory.is_dir()
                and not any(directory.iterdir())
            ):
                directory.rmdir()

    manifest = destination / EXPORT_MANIFEST
    managed = current if prune else previous | current
    temporary_manifest = manifest.with_name(f".{manifest.name}.tmp")
    temporary_manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "files": sorted(managed),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest)
    return {
        "records": count,
        "files": len(current),
        "changed": changed,
        "pruned": pruned,
        "destination": str(destination),
    }
