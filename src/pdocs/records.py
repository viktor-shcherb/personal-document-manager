from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .interfaces import Cipher


COMPONENT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class RecordError(RuntimeError):
    pass


def validate_record_id(record_id: str) -> str:
    parts = record_id.split("/")
    if not parts or any(not COMPONENT.fullmatch(part) for part in parts):
        raise RecordError(
            "Record IDs must use lowercase slash-separated ASCII components"
        )
    return record_id


def record_path(vault: Path, record_id: str) -> Path:
    validate_record_id(record_id)
    return vault / "records" / f"{record_id}.pdoc"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_record(
    *,
    vault: Path,
    cipher: Cipher,
    source_path: Path,
    record_id: str,
    title: str,
    domain: str,
    owner: str,
    lifecycle: str,
    issued_at: str | None = None,
    source_kind: str = "local",
    source_reference: str | None = None,
    thread_reference: str | None = None,
    source_profile: str | None = None,
    source_key: str | None = None,
    notes: str | None = None,
) -> Path:
    if lifecycle not in {"replaceable", "event"}:
        raise RecordError("Lifecycle must be replaceable or event")
    if not source_path.is_file():
        raise RecordError(f"Source file does not exist: {source_path}")

    destination = record_path(vault, record_id)
    if destination.exists():
        existing = read_metadata(destination, cipher)
        if existing["lifecycle"] == "event":
            raise RecordError(f"Event record already exists: {record_id}")
        if existing["lifecycle"] != lifecycle:
            raise RecordError(
                f"Cannot change lifecycle for existing record: {record_id}"
            )

    metadata = {
        "schema": 1,
        "id": record_id,
        "title": title,
        "domain": domain,
        "owner": owner,
        "lifecycle": lifecycle,
        "issued_at": issued_at,
        "imported_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source": {
            "kind": source_kind,
            "reference": source_reference,
            "thread_reference": thread_reference,
            "profile": source_profile,
            "source_key": source_key,
        },
        "content": {
            "filename": source_path.name,
            "media_type": mimetypes.guess_type(source_path.name)[0]
            or "application/octet-stream",
            "sha256": sha256(source_path),
        },
    }
    if notes:
        metadata["notes"] = notes

    with tempfile.TemporaryDirectory() as temporary_dir:
        temporary = Path(temporary_dir)
        package = temporary / "record.tar"
        metadata_path = temporary / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with tarfile.open(package, "w") as archive:
            archive.add(metadata_path, arcname="metadata.json")
            archive.add(source_path, arcname=f"content/{source_path.name}")
        cipher.seal(package, destination)
    return destination


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise RecordError("Unsafe path in encrypted record")
    archive.extractall(destination, filter="data")


def unpack_record(
    encrypted_path: Path,
    cipher: Cipher,
    destination: Path,
) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary_dir:
        package = Path(temporary_dir) / "record.tar"
        cipher.unseal(encrypted_path, package)
        with tarfile.open(package, "r") as archive:
            _safe_extract(archive, destination)
    metadata_path = destination / "metadata.json"
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def read_metadata(encrypted_path: Path, cipher: Cipher) -> dict:
    with tempfile.TemporaryDirectory() as temporary_dir:
        return unpack_record(encrypted_path, cipher, Path(temporary_dir))


def iter_record_paths(vault: Path):
    records = vault / "records"
    if not records.exists():
        return
    yield from sorted(records.rglob("*.pdoc"))


def list_records(vault: Path, cipher: Cipher) -> list[dict]:
    return [read_metadata(path, cipher) for path in iter_record_paths(vault)]


def extract_record(
    vault: Path,
    cipher: Cipher,
    record_id: str,
    output: Path,
) -> Path:
    encrypted = record_path(vault, record_id)
    if not encrypted.exists():
        raise RecordError(f"Record not found: {record_id}")
    with tempfile.TemporaryDirectory() as temporary_dir:
        temporary = Path(temporary_dir)
        metadata = unpack_record(encrypted, cipher, temporary)
        content = temporary / "content" / metadata["content"]["filename"]
        if output.exists() and output.is_dir():
            destination = output / content.name
        else:
            destination = output
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(content, destination)
    return destination
