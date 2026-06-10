from __future__ import annotations

from types import SimpleNamespace

import pytest

from pdocs.gmail import GmailError, GmailSource


DEPLOYMENT_ID = "00000000-0000-4000-8000-000000000001"


class ExistingSecrets:
    def get_optional(self, service: str, account: str) -> str | None:
        return "existing token"


def test_authorize_refuses_existing_token_before_opening_browser(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    oauth_client = tmp_path / "oauth.json"
    oauth_client.write_text("{}", encoding="utf-8")
    config = SimpleNamespace(
        deployment=SimpleNamespace(id=DEPLOYMENT_ID),
        gmail=SimpleNamespace(
            account="user@example.com",
            oauth_client=oauth_client,
        ),
    )

    class UnexpectedFlow:
        @classmethod
        def from_client_secrets_file(cls, *args, **kwargs):
            raise AssertionError("OAuth browser flow must not start")

    monkeypatch.setattr(
        "pdocs.gmail._google_imports",
        lambda: (None, None, UnexpectedFlow, None),
    )

    with pytest.raises(GmailError, match="already exists"):
        GmailSource(config, ExistingSecrets()).authorize()
