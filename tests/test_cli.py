from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdocs.cli import (
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
