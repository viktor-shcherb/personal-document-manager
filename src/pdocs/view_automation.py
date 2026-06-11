from __future__ import annotations

import plistlib
from pathlib import Path

from .config import AppConfig


class ViewAutomationError(RuntimeError):
    pass


def launch_agent_label(config: AppConfig) -> str:
    return f"com.pdocs.views.{config.deployment.id}"


def launch_agent_path(
    config: AppConfig,
    *,
    launch_agents: Path | None = None,
) -> Path:
    root = launch_agents or Path("~/Library/LaunchAgents").expanduser()
    return root / f"{launch_agent_label(config)}.plist"


def install_launch_agent(
    config: AppConfig,
    *,
    command: tuple[str, ...],
    launch_agents: Path | None = None,
) -> Path:
    if not command:
        raise ViewAutomationError("Automatic view refresh command is empty")
    executable = Path(command[0]).expanduser().resolve()
    if not executable.is_file():
        raise ViewAutomationError(f"PDM executable not found: {executable}")

    logs = config.paths.state / "view-refresh"
    logs.mkdir(parents=True, exist_ok=True)
    destination = launch_agent_path(config, launch_agents=launch_agents)
    destination.parent.mkdir(parents=True, exist_ok=True)
    label = launch_agent_label(config)
    data = {
        "Label": label,
        "ProgramArguments": [
            str(executable),
            *command[1:],
            "--config",
            str(config.path),
            "view",
            "refresh",
        ],
        "RunAtLoad": True,
        "StartInterval": config.views.refresh_interval_seconds,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(data, handle, sort_keys=True)
    temporary.replace(destination)
    return destination
