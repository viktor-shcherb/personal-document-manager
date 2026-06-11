from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from pdocs.config import load_config
from pdocs.view_automation import install_launch_agent, launch_agent_label


DEPLOYMENT_ID = "00000000-0000-4000-8000-000000000001"


def test_launch_agent_refreshes_configured_views_on_interval(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[deployment]
id = "{DEPLOYMENT_ID}"

[paths]
vault = "{tmp_path / "vault"}"
inbox = "{tmp_path / "inbox"}"
state = "{tmp_path / "state"}"

[views]
refresh_interval_seconds = 420

[views.local]
path = "{tmp_path / "readable"}"

[security]
gpg_binary = "gpg"
""",
        encoding="utf-8",
    )
    config = load_config(config_path)

    destination = install_launch_agent(
        config,
        python_executable=Path(sys.executable),
        launch_agents=tmp_path / "LaunchAgents",
    )
    with destination.open("rb") as handle:
        data = plistlib.load(handle)

    assert data["Label"] == launch_agent_label(config)
    assert data["StartInterval"] == 420
    assert data["ProgramArguments"] == [
        str(Path(sys.executable).resolve()),
        "-m",
        "pdocs",
        "--config",
        str(config.path),
        "view",
        "refresh",
    ]
