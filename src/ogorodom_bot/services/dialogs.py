from __future__ import annotations

import json
import sqlite3
from typing import Any

from ogorodom_bot.repositories.dialogs import DialogStateRepository


class DialogStateService:
    def __init__(self, conn: sqlite3.Connection):
        self.repo = DialogStateRepository(conn)

    def get(self, user_id: int) -> dict[str, Any] | None:
        row = self.repo.get(user_id)
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
        return {
            "user_id": row["user_id"],
            "state": row["state"],
            "payload": payload,
            "updated_at": row["updated_at"],
        }

    def set(self, user_id: int, state: str, payload: dict[str, Any] | None = None) -> None:
        self.repo.set(user_id, state, json.dumps(payload or {}, ensure_ascii=False))

    def clear(self, user_id: int) -> None:
        self.repo.clear(user_id)

    def merge_payload(self, user_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get(user_id)
        if current is None:
            raise ValueError("dialog state not found")
        payload = dict(current["payload"])
        payload.update(patch)
        self.set(user_id, current["state"], payload)
        return payload
