from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .interfaces import Cipher
from .records import RecordError, validate_record_id
from .source_ledger import isoformat, utc_now


PREFERENCE_ROOT = Path(".pdocs/state/preferences/events")
PREFERENCE_SCOPES = {"inclusion", "organization"}
INCLUSION_DECISIONS = {"add", "skip"}
LIFECYCLES = {"replaceable", "event"}


class PreferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreferenceRule:
    rule_id: str
    scope: str
    match: str
    instruction: str | None
    created_at: str
    source_kind: str | None = None
    source_profile: str | None = None
    decision: str | None = None
    domain: str | None = None
    owner: str | None = None
    lifecycle: str | None = None
    id_prefix: str | None = None

    @property
    def selector(self) -> tuple[str, str, str | None, str | None]:
        return (
            self.scope,
            _normalize_match(self.match),
            self.source_kind,
            self.source_profile,
        )

    def as_dict(self) -> dict:
        return {
            "id": self.rule_id,
            "scope": self.scope,
            "match": self.match,
            "source_kind": self.source_kind,
            "source_profile": self.source_profile,
            "decision": self.decision,
            "instruction": self.instruction,
            "domain": self.domain,
            "owner": self.owner,
            "lifecycle": self.lifecycle,
            "id_prefix": self.id_prefix,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PreferenceRule:
        return cls(
            rule_id=data["id"],
            scope=data["scope"],
            match=data["match"],
            source_kind=data.get("source_kind"),
            source_profile=data.get("source_profile"),
            decision=data.get("decision"),
            instruction=data.get("instruction"),
            domain=data.get("domain"),
            owner=data.get("owner"),
            lifecycle=data.get("lifecycle"),
            id_prefix=data.get("id_prefix"),
            created_at=data["created_at"],
        )


def _normalize_text(value: str, label: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise PreferenceError(f"{label} must not be empty")
    return normalized


def _normalize_match(value: str) -> str:
    return _normalize_text(value, "Preference match").casefold()


def _normalize_optional(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _normalize_text(value, label)


def _new_rule_id() -> str:
    return f"pref-{uuid.uuid4().hex[:12]}"


class PreferenceStore:
    def __init__(self, vault: Path, cipher: Cipher):
        self.vault = vault
        self.cipher = cipher
        self.events = vault / PREFERENCE_ROOT

    def _read_event(self, path: Path) -> dict:
        with tempfile.TemporaryDirectory() as temporary_dir:
            plaintext = Path(temporary_dir) / "event.json"
            self.cipher.unseal(path, plaintext)
            try:
                event = json.loads(plaintext.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise PreferenceError(f"Invalid preference event: {path}") from error
        if event.get("schema") != 1:
            raise PreferenceError(f"Unsupported preference schema in {path}")
        return event

    def iter_events(self):
        if not self.events.exists():
            return
        for path in sorted(self.events.glob("*.pdoc")):
            yield path, self._read_event(path)

    def _rules(self, *, validate_conflicts: bool) -> dict[str, PreferenceRule]:
        rules: dict[str, PreferenceRule] = {}
        for _, event in self.iter_events():
            event_type = event.get("event")
            if event_type == "remember":
                rule = PreferenceRule.from_dict(event["rule"])
                rules[rule.rule_id] = rule
            elif event_type == "forget":
                rules.pop(event["rule_id"], None)
            else:
                raise PreferenceError(
                    f"Unsupported preference event type: {event_type!r}"
                )
        if validate_conflicts:
            selectors: dict[tuple[str, str, str | None, str | None], str] = {}
            for rule in rules.values():
                conflicting_id = selectors.get(rule.selector)
                if conflicting_id:
                    raise PreferenceError(
                        f"Conflicting active preferences {conflicting_id} and "
                        f"{rule.rule_id}; forget one before continuing"
                    )
                selectors[rule.selector] = rule.rule_id
        return rules

    def rules(self) -> dict[str, PreferenceRule]:
        return self._rules(validate_conflicts=True)

    def rule(self, rule_id: str) -> PreferenceRule | None:
        return self.rules().get(rule_id)

    def _write(self, event: dict) -> Path:
        self.events.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        destination = self.events / f"{timestamp}_{uuid.uuid4().hex}.pdoc"
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

    def remember(
        self,
        *,
        scope: str,
        match: str,
        instruction: str | None = None,
        source_kind: str | None = None,
        source_profile: str | None = None,
        decision: str | None = None,
        domain: str | None = None,
        owner: str | None = None,
        lifecycle: str | None = None,
        id_prefix: str | None = None,
        now: datetime | None = None,
    ) -> tuple[PreferenceRule, Path]:
        if scope not in PREFERENCE_SCOPES:
            raise PreferenceError(f"Unsupported preference scope: {scope!r}")
        match = _normalize_text(match, "Preference match")
        instruction = _normalize_optional(instruction, "Preference instruction")
        source_kind = _normalize_optional(source_kind, "Source kind")
        source_profile = _normalize_optional(source_profile, "Source profile")
        domain = _normalize_optional(domain, "Organization domain")
        owner = _normalize_optional(owner, "Organization owner")
        id_prefix = _normalize_optional(id_prefix, "Organization ID prefix")
        if id_prefix:
            try:
                validate_record_id(id_prefix)
            except RecordError as error:
                raise PreferenceError(
                    f"Invalid organization ID prefix: {id_prefix!r}"
                ) from error

        if scope == "inclusion":
            if decision not in INCLUSION_DECISIONS:
                raise PreferenceError(
                    "Inclusion preferences require decision add or skip"
                )
            if any((domain, owner, lifecycle, id_prefix)):
                raise PreferenceError(
                    "Organization fields are valid only for organization preferences"
                )
        else:
            if decision is not None:
                raise PreferenceError(
                    "Organization preferences do not accept an inclusion decision"
                )
            if lifecycle and lifecycle not in LIFECYCLES:
                raise PreferenceError(
                    "Organization lifecycle must be replaceable or event"
                )
            if not any((instruction, domain, owner, lifecycle, id_prefix)):
                raise PreferenceError(
                    "Organization preferences require an instruction or "
                    "organization field"
                )

        created_at = isoformat((now or utc_now()).astimezone(UTC))
        rule = PreferenceRule(
            rule_id=_new_rule_id(),
            scope=scope,
            match=match,
            source_kind=source_kind,
            source_profile=source_profile,
            decision=decision,
            instruction=instruction,
            domain=domain,
            owner=owner,
            lifecycle=lifecycle,
            id_prefix=id_prefix,
            created_at=created_at,
        )
        for existing in self.rules().values():
            if existing.selector == rule.selector:
                raise PreferenceError(
                    f"Preference selector already exists as {existing.rule_id}; "
                    "forget it before recording a replacement"
                )

        event = self._write(
            {
                "schema": 1,
                "event": "remember",
                "recorded_at": created_at,
                "rule": rule.as_dict(),
            }
        )
        return rule, event

    def forget(self, rule_id: str, *, now: datetime | None = None) -> Path:
        if rule_id not in self._rules(validate_conflicts=False):
            raise PreferenceError(f"Preference not found: {rule_id}")
        return self._write(
            {
                "schema": 1,
                "event": "forget",
                "rule_id": rule_id,
                "recorded_at": isoformat((now or utc_now()).astimezone(UTC)),
            }
        )
