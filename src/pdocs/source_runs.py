from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import (
    AppConfig,
    FolderSourceProfile,
    GmailSourceProfile,
    validate_source_profile_name,
)
from .folder_exchange import (
    FolderCandidate,
    discover_folder,
    resolve_ingest_folder,
    stage_folder_candidates,
)
from .gmail import GmailSource
from .interfaces import Cipher
from .records import sha256
from .source_ledger import (
    SourceLedger,
    SourceLedgerError,
    SourceRunLock,
    isoformat,
    new_run_id,
    parse_duration,
    parse_time,
    source_key,
    utc_now,
    write_failure,
)


@dataclass(frozen=True)
class SourceRunResult:
    source_key: str
    run_id: str
    query: str | None
    items_seen: int
    items_exported: int
    items_skipped_duplicate: int
    batch: Path | None
    ledger_event: Path


def gmail_profile(config: AppConfig, name: str) -> GmailSourceProfile:
    validate_source_profile_name(name)
    try:
        return config.sources.gmail[name]
    except KeyError as error:
        available = ", ".join(sorted(config.sources.gmail)) or "none"
        raise SourceLedgerError(
            f"Unknown Gmail source profile {name!r}; configured profiles: {available}"
        ) from error


def folder_profile(
    config: AppConfig,
    name: str,
    override: Path | None = None,
) -> FolderSourceProfile:
    validate_source_profile_name(name)
    if override:
        root = override.expanduser().resolve()
        return FolderSourceProfile(
            name=name,
            root=root,
            inbox=".",
            views="Views",
            extensions=(".pdf", ".jpg", ".jpeg", ".png", ".heic"),
        )
    try:
        return config.sources.folder[name]
    except KeyError as error:
        available = ", ".join(sorted(config.sources.folder)) or "none"
        raise SourceLedgerError(
            f"Unknown folder source profile {name!r}; configured profiles: {available}"
        ) from error


def gmail_source_identity(config: AppConfig, profile: GmailSourceProfile) -> dict:
    return {
        "provider": "gmail",
        "account": config.gmail.account,
        "query": profile.query,
    }


def folder_source_identity(
    profile: FolderSourceProfile,
    folder_override: Path | None = None,
) -> dict:
    identity = {
        "provider": "folder",
        "profile": profile.name,
    }
    if folder_override:
        identity["root"] = str(folder_override.expanduser().resolve())
    return identity


def _validate_folder_source(config: AppConfig, folder: Path) -> None:
    protected = {
        "vault": config.paths.vault.resolve(),
        "local inbox": config.paths.inbox.resolve(),
        "readable view": config.paths.readable.resolve(),
    }
    resolved = folder.resolve()
    for name, path in protected.items():
        if resolved == path or resolved in path.parents or path in resolved.parents:
            raise SourceLedgerError(
                f"Folder source must not overlap the configured {name}: {resolved}"
            )


def _known_pairs(state) -> set[tuple[str, str | None]]:
    if not state:
        return set()
    return {
        (item["source_item_id"], item.get("content_sha256"))
        for item in state.seen_items
    }


def _gmail_query(
    *,
    profile: GmailSourceProfile,
    state,
    now: datetime,
    full: bool,
    since: str | None,
    overlap: str | None,
) -> tuple[str, str | None, str]:
    start = None
    if since:
        start = parse_time(since)
    elif not full:
        if state and state.last_completed_source_time:
            start = parse_time(state.last_completed_source_time) - parse_duration(
                overlap or profile.overlap_window
            )
        else:
            start = now - parse_duration(profile.initial_window)

    query = profile.query
    if start:
        query = f"{query} after:{start.strftime('%Y/%m/%d')}".strip()
    end_date = (now + timedelta(days=1)).date().isoformat().replace("-", "/")
    query = f"{query} before:{end_date}".strip()
    return query, isoformat(start) if start else None, isoformat(now)


def run_gmail_source(
    *,
    config: AppConfig,
    cipher: Cipher,
    gmail: GmailSource,
    profile_name: str,
    full: bool = False,
    since: str | None = None,
    overlap: str | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> SourceRunResult:
    profile = gmail_profile(config, profile_name)
    identity = gmail_source_identity(config, profile)
    key = source_key("gmail", profile.name, identity)
    ledger = SourceLedger(config.paths.vault, cipher)
    state = ledger.state(key)
    run_now = (now or utc_now()).astimezone(UTC).replace(microsecond=0)
    query, window_start, window_end = _gmail_query(
        profile=profile,
        state=state,
        now=run_now,
        full=full,
        since=since,
        overlap=overlap,
    )
    run_id = new_run_id("gmail", profile.name, run_now)
    started_at = isoformat(run_now)
    known_ids = (
        {item["source_item_id"] for item in state.seen_items} if state else set()
    )
    all_hashes = ledger.seen_content_hashes()
    event_items = []
    exported = 0
    duplicates = 0
    batch = None

    try:
        with SourceRunLock(config.paths.state, key, run_id):
            candidates = gmail.search(query, limit)
            for candidate in candidates:
                if candidate.reference in known_ids:
                    duplicates += 1
                    continue
                destination = (
                    config.paths.inbox / "email" / candidate.reference
                )
                existed = destination.exists()
                exported_path = gmail.export(candidate.reference)
                content = exported_path / "message.eml"
                digest = sha256(content)
                duplicate_content = digest in all_hashes
                if duplicate_content:
                    duplicates += 1
                    if not existed:
                        shutil.rmtree(exported_path)
                else:
                    exported += 1
                    batch = config.paths.inbox / "email"
                    all_hashes.add(digest)
                    source_manifest = exported_path / "source.json"
                    source_data = json.loads(source_manifest.read_text(encoding="utf-8"))
                    source_data.update(
                        {
                            "source_profile": profile.name,
                            "source_key": key,
                            "content_sha256": digest,
                        }
                    )
                    source_manifest.write_text(
                        json.dumps(source_data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                event_items.append(
                    {
                        "source_item_id": candidate.reference,
                        "source_ref": f"gmail://message/{candidate.reference}",
                        "thread_reference": candidate.thread_reference,
                        "content_sha256": digest,
                        "source_time": candidate.source_time,
                        "exported": not duplicate_content,
                    }
                )

            completed_at = isoformat(utc_now())
            event = ledger.complete(
                key=key,
                kind="gmail",
                profile=profile.name,
                identity=identity,
                run={
                    "run_id": run_id,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "source_window_start": window_start,
                    "source_window_end": window_end,
                    "last_completed_source_time": window_end,
                    "query": query,
                    "items_seen": len(candidates),
                    "items_exported": exported,
                    "items_skipped_duplicate": duplicates,
                },
                items=event_items,
            )
    except Exception as error:
        write_failure(
            config.paths.state,
            run_id=run_id,
            source_key_value=key,
            error=error,
        )
        raise
    return SourceRunResult(
        source_key=key,
        run_id=run_id,
        query=query,
        items_seen=len(candidates),
        items_exported=exported,
        items_skipped_duplicate=duplicates,
        batch=batch,
        ledger_event=event,
    )


def _new_folder_candidates(
    candidates: list[FolderCandidate],
    *,
    known_pairs: set[tuple[str, str | None]],
    known_hashes: set[str],
) -> tuple[list[FolderCandidate], list[dict], int]:
    exports = []
    event_items = []
    duplicates = 0
    for candidate in candidates:
        identity = (candidate.relative_path, candidate.content_sha256)
        duplicate = identity in known_pairs or candidate.content_sha256 in known_hashes
        if duplicate:
            duplicates += 1
        else:
            exports.append(candidate)
            known_hashes.add(candidate.content_sha256)
        if identity not in known_pairs:
            event_items.append(
                {
                    "source_item_id": candidate.relative_path,
                    "source_ref": candidate.relative_path,
                    "content_sha256": candidate.content_sha256,
                    "source_time": candidate.modified_at,
                    "size": candidate.size,
                    "exported": not duplicate,
                }
            )
    return exports, event_items, duplicates


def run_folder_source(
    *,
    config: AppConfig,
    cipher: Cipher,
    profile_name: str,
    folder_override: Path | None = None,
    full: bool = False,
    now: datetime | None = None,
) -> SourceRunResult:
    profile = folder_profile(config, profile_name, folder_override)
    folder = resolve_ingest_folder(profile, folder_override)
    _validate_folder_source(config, folder)
    identity = folder_source_identity(profile, folder_override)
    key = source_key("folder", profile.name, identity)
    ledger = SourceLedger(config.paths.vault, cipher)
    state = None if full else ledger.state(key)
    run_now = (now or utc_now()).astimezone(UTC).replace(microsecond=0)
    run_id = new_run_id("folder", profile.name, run_now)
    started_at = isoformat(run_now)
    candidates = []

    try:
        with SourceRunLock(config.paths.state, key, run_id):
            candidates = discover_folder(folder, extensions=profile.extensions)
            exports, event_items, duplicates = _new_folder_candidates(
                candidates,
                known_pairs=_known_pairs(state),
                known_hashes=ledger.seen_content_hashes(),
            )
            batch, _ = stage_folder_candidates(
                exports,
                inbox=config.paths.inbox,
                profile=profile.name,
                run_id=run_id,
                source_key=key,
            )
            completed_at = isoformat(utc_now())
            event = ledger.complete(
                key=key,
                kind="folder",
                profile=profile.name,
                identity=identity,
                run={
                    "run_id": run_id,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "source_window_start": None,
                    "source_window_end": isoformat(run_now),
                    "last_completed_source_time": isoformat(run_now),
                    "items_seen": len(candidates),
                    "items_exported": len(exports),
                    "items_skipped_duplicate": duplicates,
                    "full_rescan": full,
                },
                items=event_items,
            )
    except Exception as error:
        write_failure(
            config.paths.state,
            run_id=run_id,
            source_key_value=key,
            error=error,
        )
        raise
    return SourceRunResult(
        source_key=key,
        run_id=run_id,
        query=None,
        items_seen=len(candidates),
        items_exported=len(exports),
        items_skipped_duplicate=duplicates,
        batch=batch,
        ledger_event=event,
    )
