from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


class TelegramApi:
    def __init__(self, token: str, timeout: int = 30):
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        data = self._post("getUpdates", payload)
        return data.get("result", [])

    def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._post("sendMessage", payload)

    def answer_callback_query(
        self, callback_query_id: str, text: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return self._post("answerCallbackQuery", payload)

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._post("editMessageText", payload)

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = urllib.parse.urlencode(
            {
                key: json.dumps(value) if isinstance(value, (list, dict)) else value
                for key, value in payload.items()
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
