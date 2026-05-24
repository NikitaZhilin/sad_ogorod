from __future__ import annotations

import sqlite3

from ogorodom_bot.repositories.users import UserRepository


class PrivacyService:
    def __init__(self, conn: sqlite3.Connection):
        self.users = UserRepository(conn)

    def delete_user_data(self, user_id: int) -> None:
        self.users.delete(user_id)
