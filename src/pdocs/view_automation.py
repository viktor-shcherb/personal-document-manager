from __future__ import annotations

import os
import plistlib
import shutil
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
    gpg_executable = shutil.which(config.security.gpg_binary)
    if not gpg_executable:
        raise ViewAutomationError(
            f"GnuPG executable not found: {config.security.gpg_binary}"
        )
    path_entries = [
        str(executable.parent),
        str(Path(gpg_executable).resolve().parent),
        *os.environ.get("PATH", "").split(os.pathsep),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    environment_path = os.pathsep.join(dict.fromkeys(filter(None, path_entries)))

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
        "EnvironmentVariables": {
            "PATH": environment_path,
        },
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(data, handle, sort_keys=True)
    temporary.replace(destination)
    return destination
