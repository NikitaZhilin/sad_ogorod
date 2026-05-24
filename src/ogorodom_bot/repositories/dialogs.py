from __future__ import annotations

from ogorodom_bot.repositories.base import Repository


class DialogStateRepository(Repository):
    def get(self, user_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM dialog_states WHERE user_id = ?", (user_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def set(self, user_id: int, state: str, payload_json: str) -> None:
        self.conn.execute(
            """
            INSERT INTO dialog_states(user_id, state, payload_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                state = excluded.state,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, state, payload_json),
        )

    def clear(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM dialog_states WHERE user_id = ?", (user_id,))
