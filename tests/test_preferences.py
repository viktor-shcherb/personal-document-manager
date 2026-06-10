from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdocs.preferences import PreferenceError, PreferenceStore


class XorCipher:
    def seal(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(bytes(value ^ 0xA5 for value in source.read_bytes()))

    def unseal(self, source: Path, destination: Path) -> None:
        destination.write_bytes(bytes(value ^ 0xA5 for value in source.read_bytes()))


def test_encrypted_inclusion_preference_replays_across_devices(tmp_path: Path):
    cipher = XorCipher()
    first_vault = tmp_path / "first"
    store = PreferenceStore(first_vault, cipher)
    rule, event = store.remember(
        scope="inclusion",
        match="Monthly bank statements from Example Bank",
        decision="add",
        instruction="Retain each statement without asking again.",
        source_kind="gmail",
        now=datetime(2026, 6, 10, 10, tzinfo=UTC),
    )

    assert b"Example Bank" not in event.read_bytes()

    second_vault = tmp_path / "second"
    shutil.copytree(first_vault, second_vault)
    replayed = PreferenceStore(second_vault, cipher).rule(rule.rule_id)

    assert replayed is not None
    assert replayed.decision == "add"
    assert replayed.source_kind == "gmail"


def test_organization_preference_preserves_structured_defaults(tmp_path: Path):
    store = PreferenceStore(tmp_path / "vault", XorCipher())

    rule, _ = store.remember(
        scope="organization",
        match="Monthly bank statements",
        instruction="Group by institution and year.",
        domain="finance-insurance",
        owner="self",
        lifecycle="event",
        id_prefix="finance-insurance/banking/statements",
    )

    assert rule.domain == "finance-insurance"
    assert rule.lifecycle == "event"
    assert rule.id_prefix == "finance-insurance/banking/statements"


def test_duplicate_selector_requires_explicit_forget_before_replacement(
    tmp_path: Path,
):
    store = PreferenceStore(tmp_path / "vault", XorCipher())
    first, _ = store.remember(
        scope="inclusion",
        match="Utility bills",
        decision="skip",
    )

    with pytest.raises(PreferenceError, match=first.rule_id):
        store.remember(
            scope="inclusion",
            match="  utility   bills ",
            decision="add",
        )


def test_forget_retires_rule_without_deleting_encrypted_history(tmp_path: Path):
    store = PreferenceStore(tmp_path / "vault", XorCipher())
    rule, _ = store.remember(
        scope="inclusion",
        match="Routine delivery notifications",
        decision="skip",
    )
    store.forget(rule.rule_id)

    assert store.rule(rule.rule_id) is None
    assert len(list(store.events.glob("*.pdoc"))) == 2


def test_organization_preference_rejects_invalid_record_id_prefix(tmp_path: Path):
    store = PreferenceStore(tmp_path / "vault", XorCipher())

    with pytest.raises(PreferenceError, match="Invalid organization ID prefix"):
        store.remember(
            scope="organization",
            match="Statements",
            id_prefix="../outside",
        )


def test_replay_rejects_conflicting_active_rules_from_two_devices(tmp_path: Path):
    cipher = XorCipher()
    first = PreferenceStore(tmp_path / "first", cipher)
    second = PreferenceStore(tmp_path / "second", cipher)
    first.remember(
        scope="inclusion",
        match="Tax newsletters",
        decision="skip",
    )
    second.remember(
        scope="inclusion",
        match="Tax newsletters",
        decision="add",
    )
    merged = tmp_path / "merged"
    merged_events = merged / ".pdocs/state/preferences/events"
    merged_events.mkdir(parents=True)
    for event in first.events.glob("*.pdoc"):
        shutil.copy2(event, merged_events / event.name)
    for event in second.events.glob("*.pdoc"):
        shutil.copy2(event, merged_events / event.name)

    merged_store = PreferenceStore(merged, cipher)
    with pytest.raises(PreferenceError, match="Conflicting active preferences"):
        merged_store.rules()

    conflicting_ids = [
        event["rule"]["id"]
        for _, event in merged_store.iter_events()
        if event["event"] == "remember"
    ]
    merged_store.forget(conflicting_ids[0])

    assert len(merged_store.rules()) == 1
