from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdocs.cli import (
    _paths_overlap,
    _print_source_run,
    build_parser,
    _initialize_repository_secret,
    _repair_keychain_access,
    _validate_record_input,
)

DEPLOYMENT_ID = "00000000-0000-4000-8000-000000000001"


def _config(domains: list[str]):
    return SimpleNamespace(raw={"taxonomy": {"domains": domains}})


def test_record_input_rejects_unknown_configured_domain():
    args = SimpleNamespace(domain="employmnt", issued_at="2026-06-10")

    with pytest.raises(ValueError, match="configured domains: employment"):
        _validate_record_input(_config(["employment"]), args)


def test_record_input_rejects_non_iso_issue_date():
    args = SimpleNamespace(domain="employment", issued_at="June 10, 2026")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _validate_record_input(_config(["employment"]), args)


def test_record_input_rejects_alternative_iso_date_form():
    args = SimpleNamespace(domain="employment", issued_at="2026-W24-3")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _validate_record_input(_config(["employment"]), args)


def test_record_input_allows_configured_domain_and_iso_date():
    args = SimpleNamespace(domain="employment", issued_at="2026-06-10")

    _validate_record_input(_config(["employment"]), args)


def test_repair_keychain_access_preserves_secret():
    class MemoryKeychain:
        def __init__(self):
            self.value = "existing encryption secret"

        def repair_access(self, service: str, account: str) -> None:
            assert service == "pdocs.repository-encryption"
            assert account == DEPLOYMENT_ID

    config = SimpleNamespace(
        deployment=SimpleNamespace(id=DEPLOYMENT_ID),
    )
    keychain = MemoryKeychain()

    _repair_keychain_access(config, keychain)

    assert keychain.value == "existing encryption secret"


def test_init_uses_create_only_keychain_write():
    class MemoryKeychain:
        def __init__(self):
            self.created = None

        def create(self, service: str, account: str, value: str) -> None:
            self.created = (service, account, value)

    config = SimpleNamespace(
        deployment=SimpleNamespace(id=DEPLOYMENT_ID),
    )
    keychain = MemoryKeychain()

    _initialize_repository_secret(config, keychain)

    assert keychain.created is not None
    assert keychain.created[:2] == (
        "pdocs.repository-encryption",
        DEPLOYMENT_ID,
    )


def test_parser_accepts_ledger_backed_source_commands():
    email = build_parser().parse_args(
        [
            "source",
            "run",
            "email",
            "--profile",
            "documents",
            "--since",
            "2026-01-01",
        ]
    )
    folder = build_parser().parse_args(
        ["ingest", "folder", "--profile", "iphone", "--full"]
    )
    state = build_parser().parse_args(
        [
            "source",
            "state",
            "show",
            "folder",
            "--folder",
            "/tmp/exchange",
        ]
    )

    assert email.source_run_kind == "email"
    assert email.profile == "documents"
    assert email.since == "2026-01-01"
    assert folder.ingest_command == "folder"
    assert folder.profile == "iphone"
    assert folder.full is True
    assert state.folder.as_posix() == "/tmp/exchange"


def test_parser_accepts_inclusion_and_organization_preferences():
    inclusion = build_parser().parse_args(
        [
            "preference",
            "remember",
            "inclusion",
            "--match",
            "monthly bank statements from Example Bank",
            "--decision",
            "add",
            "--source-kind",
            "gmail",
        ]
    )
    organization = build_parser().parse_args(
        [
            "preference",
            "remember",
            "organization",
            "--match",
            "monthly bank statements",
            "--domain",
            "finance-insurance",
            "--lifecycle",
            "event",
            "--id-prefix",
            "finance-insurance/banking/statements",
        ]
    )

    assert inclusion.preference_scope == "inclusion"
    assert inclusion.decision == "add"
    assert organization.preference_scope == "organization"
    assert organization.lifecycle == "event"


def test_source_run_output_tells_agent_to_commit_ledger(capsys):
    result = SimpleNamespace(
        source_key="gmail:documents:key",
        run_id="run-1",
        query="has:attachment",
        items_seen=2,
        items_exported=1,
        items_skipped_duplicate=1,
        batch="/tmp/inbox",
        ledger_event="/vault/.pdocs/state/source-ledger/events/event.pdoc",
    )

    _print_source_run(result)

    output = capsys.readouterr().out
    assert "encrypted ledger event:" in output
    assert "records/ and .pdocs/state/source-ledger/" in output


def test_paths_overlap_rejects_equal_parent_and_child(tmp_path):
    root = tmp_path / "root"
    child = root / "child"

    assert _paths_overlap(root, root)
    assert _paths_overlap(root, child)
    assert _paths_overlap(child, root)
    assert not _paths_overlap(root, tmp_path / "other")
