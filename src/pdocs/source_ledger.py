from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .interfaces import Cipher


LEDGER_ROOT = Path(".pdocs/state/source-ledger/events")
LOCAL_INDEX = "source-ledger-index.json"
DURATION = re.compile(r"^(\d+)([smhdw])$")


class SourceLedgerError(RuntimeError):
    pass


@dataclass
class SourceState:
    source_key: str
    source_kind: str
    source_profile: str
    source_identity: dict = field(default_factory=dict)
    completed_runs: list[dict] = field(default_factory=list)
    seen_items: list[dict] = field(default_factory=list)

    @property
    def last_successful_run_at(self) -> str | None:
        if not self.completed_runs:
            return None
        return max(run["completed_at"] for run in self.completed_runs)

    @property
    def last_completed_source_time(self) -> str | None:
        values = [
            run["last_completed_source_time"]
            for run in self.completed_runs
            if run.get("last_completed_source_time")
        ]
        if not values:
            return None
        return max(values)

    def as_dict(self) -> dict:
        return {
            "source_key": self.source_key,
            "source_kind": self.source_kind,
            "source_profile": self.source_profile,
            "source_identity": self.source_identity,
            "last_successful_run_at": self.last_successful_run_at,
            "last_completed_source_time": self.last_completed_source_time,
            "completed_runs": self.completed_runs,
            "seen_items": self.seen_items,
        }


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def parse_time(value: str) -> datetime:
    normalized = value.strip()
    if len(normalized) == 10:
        normalized += "T00:00:00+00:00"
    elif normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise SourceLedgerError(
            f"Invalid time {value!r}; use YYYY-MM-DD or ISO 8601"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_duration(value: str) -> timedelta:
    match = DURATION.fullmatch(value.strip().lower())
    if not match:
        raise SourceLedgerError(
            f"Invalid duration {value!r}; use a number followed by s, m, h, d, or w"
        )
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }[unit]
    return timedelta(seconds=amount * seconds)


def source_key(kind: str, profile: str, identity: dict) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{kind}:{profile}:{fingerprint}"


def new_run_id(kind: str, profile: str, now: datetime | None = None) -> str:
    timestamp = (now or utc_now()).strftime("%Y-%m-%dT%H-%M-%SZ")
    safe_profile = re.sub(r"[^a-zA-Z0-9._-]+", "-", profile)
    return f"{timestamp}_{kind}_{safe_profile}_{uuid.uuid4().hex[:8]}"


class SourceLedger:
    def __init__(self, vault: Path, cipher: Cipher):
        self.vault = vault
        self.cipher = cipher
        self.events = vault / LEDGER_ROOT

    def _read_event(self, path: Path) -> dict:
        with tempfile.TemporaryDirectory() as temporary_dir:
            plaintext = Path(temporary_dir) / "event.json"
            self.cipher.unseal(path, plaintext)
            try:
                event = json.loads(plaintext.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise SourceLedgerError(
                    f"Invalid source ledger event: {path}"
                ) from error
        if event.get("schema") != 1:
            raise SourceLedgerError(f"Unsupported source ledger schema in {path}")
        return event

    def iter_events(self):
        if not self.events.exists():
            return
        for path in sorted(self.events.glob("*.pdoc")):
            yield path, self._read_event(path)

    def states(self) -> dict[str, SourceState]:
        states: dict[str, SourceState] = {}
        for _, event in self.iter_events():
            key = event["source_key"]
            if event["event"] == "reset":
                states.pop(key, None)
                continue
            if event["event"] != "completed-run":
                raise SourceLedgerError(
                    f"Unsupported source ledger event type: {event['event']!r}"
                )
            state = states.setdefault(
                key,
                SourceState(
                    source_key=key,
                    source_kind=event["source_kind"],
                    source_profile=event["source_profile"],
                    source_identity=event.get("source_identity", {}),
                ),
            )
            state.completed_runs.append(event["run"])
            existing = {
                (item["source_item_id"], item.get("content_sha256"))
                for item in state.seen_items
            }
            for item in event.get("items", ()):
                identity = (item["source_item_id"], item.get("content_sha256"))
                if identity not in existing:
                    state.seen_items.append(item)
                    existing.add(identity)
        return states

    def state(self, key: str) -> SourceState | None:
        return self.states().get(key)

    def seen_content_hashes(self) -> set[str]:
        return {
            item["content_sha256"]
            for state in self.states().values()
            for item in state.seen_items
            if item.get("content_sha256")
        }

    def _write(self, event: dict) -> Path:
        self.events.mkdir(parents=True, exist_ok=True)
        event_id = uuid.uuid4().hex
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        destination = self.events / f"{timestamp}_{event_id}.pdoc"
        temporary_destination = self.events / f".{destination.name}.tmp"
        with tempfile.TemporaryDirectory() as temporary_dir:
            plaintext = Path(temporary_dir) / "event.json"
            plaintext.write_text(
                json.dumps(event, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            try:
                self.cipher.seal(plaintext, temporary_destination)
                temporary_destination.replace(destination)
            finally:
                temporary_destination.unlink(missing_ok=True)
        return destination

    def complete(
        self,
        *,
        key: str,
        kind: str,
        profile: str,
        identity: dict,
        run: dict,
        items: list[dict],
    ) -> Path:
        return self._write(
            {
                "schema": 1,
                "event": "completed-run",
                "source_key": key,
                "source_kind": kind,
                "source_profile": profile,
                "source_identity": identity,
                "run": run,
                "items": items,
            }
        )

    def reset(self, key: str, *, kind: str, profile: str) -> Path:
        return self._write(
            {
                "schema": 1,
                "event": "reset",
                "source_key": key,
                "source_kind": kind,
                "source_profile": profile,
                "reset_at": isoformat(utc_now()),
            }
        )

    def rebuild_local_index(self, state_dir: Path) -> Path:
        destination = state_dir / LOCAL_INDEX
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                [state.as_dict() for state in self.states().values()],
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        return destination


class SourceRunLock(AbstractContextManager):
    def __init__(self, state_dir: Path, key: str, run_id: str):
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        self.path = state_dir / "source-runs" / "locks" / f"{digest}.lock"
        self.run_id = run_id
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as error:
            raise SourceLedgerError(
                f"Source run is already active; remove stale lock only after "
                f"inspection: {self.path}"
            ) from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "run_id": self.run_id,
                    "pid": os.getpid(),
                    "started_at": isoformat(utc_now()),
                },
                handle,
            )
            handle.write("\n")
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.acquired:
            self.path.unlink(missing_ok=True)
        return False


def write_failure(
    state_dir: Path,
    *,
    run_id: str,
    source_key_value: str,
    error: Exception,
) -> Path:
    failures = state_dir / "source-runs" / "failures"
    failures.mkdir(parents=True, exist_ok=True)
    destination = failures / f"{run_id}.json"
    destination.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source_key": source_key_value,
                "failed_at": isoformat(utc_now()),
                "error_type": type(error).__name__,
                "error": str(error),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(destination, 0o600)
    return destination
