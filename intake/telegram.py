"""Small, deliberately quiet Telegram Bot API client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class TelegramError(RuntimeError):
    """A Telegram request failed; details intentionally exclude response data."""


class TelegramClient:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}/"

    def _call(self, method: str, payload: dict) -> object:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._base_url + method,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                reply = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
            raise TelegramError("Telegram API request failed") from exc
        if not isinstance(reply, dict) or not reply.get("ok"):
            raise TelegramError("Telegram API returned an error")
        return reply.get("result")

    def get_updates(self, offset: int) -> list[dict]:
        result = self._call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message"]})
        if not isinstance(result, list):
            raise TelegramError("Telegram API returned an invalid updates response")
        return [update for update in result if isinstance(update, dict)]

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})
