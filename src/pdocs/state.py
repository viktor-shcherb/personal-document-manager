from __future__ import annotations

import json
from pathlib import Path


class ReviewState:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "gmail-reviewed.json"

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        return set(json.loads(self.path.read_text(encoding="utf-8")))

    def pending(self, message_ids: list[str]) -> list[str]:
        reviewed = self._load()
        return [message_id for message_id in message_ids if message_id not in reviewed]

    def mark(self, message_ids: list[str]) -> None:
        reviewed = self._load()
        reviewed.update(message_ids)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(sorted(reviewed), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
