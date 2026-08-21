"""Poll Telegram and create GitHub Project draft items safely."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intake.project import ProjectClient
from intake.telegram import TelegramClient

CURSOR_PATH = Path("state/offset.json")
COMMAND = re.compile(r"^/(bug|idea|note)(?:@[^\s]+)?(?=\s|$)", re.IGNORECASE)
TYPE_OPTIONS = {"bug": "Bug", "idea": "Feature", "note": "Observation"}


def log(message: str) -> None:
    print(message, file=sys.stderr)


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def required_integer(name: str) -> int:
    try:
        return int(required(name))
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be numeric") from exc


def read_cursor(path: Path = CURSOR_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        offset, processed = data["offset"], data["processed_update_ids"]
        if not isinstance(offset, int) or not isinstance(processed, list) or not all(isinstance(i, int) for i in processed):
            raise ValueError("invalid cursor")
        return {"offset": offset, "processed_update_ids": processed[-200:]}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        log("Cursor unavailable; starting from offset 0.")
        return {"offset": 0, "processed_update_ids": []}


def write_cursor(cursor: dict, path: Path = CURSOR_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cursor, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_message(text: str) -> tuple[str, str]:
    stripped = text.lstrip()
    match = COMMAND.match(stripped)
    if not match:
        return "note", stripped
    return match.group(1).lower(), stripped[match.end():].lstrip()


def make_title(text: str) -> str:
    title = text.splitlines()[0].strip() if text.splitlines() else ""
    return title if len(title) <= 80 else title[:79].rstrip() + "…"


def mark_processed(cursor: dict, update_id: int) -> None:
    cursor["processed_update_ids"] = (cursor["processed_update_ids"] + [update_id])[-200:]
    cursor["offset"] = update_id + 1


def option_id(field: dict | None, name: str) -> str | None:
    if not field:
        return None
    for option in field.get("options", []):
        if option.get("name") == name and option.get("id"):
            return option["id"]
    return None


def run(telegram: TelegramClient, project: ProjectClient, owner_id: int, cursor_path: Path = CURSOR_PATH) -> None:
    cursor = read_cursor(cursor_path)
    updates = telegram.get_updates(cursor["offset"])
    project_id = project.resolve_project()
    try:
        fields = project.resolve_fields(project_id)
    except Exception:
        # Field metadata is non-critical: messages must still become draft items.
        log("Warning: could not resolve project fields; field values will be unset.")
        fields = {}

    for update in sorted(updates, key=lambda u: u.get("update_id", -1)):
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            continue
        if update_id in cursor["processed_update_ids"]:
            mark_processed(cursor, update_id)
            write_cursor(cursor, cursor_path)
            continue
        message = update.get("message") if isinstance(update.get("message"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        if sender.get("id") != owner_id:
            log("Rejected 1 update from an unauthorized sender.")
            mark_processed(cursor, update_id)
            write_cursor(cursor, cursor_path)
            continue
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        chat_id = chat.get("id")
        text = message.get("text")
        if not isinstance(text, str):
            if isinstance(chat_id, int):
                telegram.send_message(chat_id, "Only text messages are supported for now.")
            mark_processed(cursor, update_id)
            write_cursor(cursor, cursor_path)
            continue
        kind, content = parse_message(text)
        captured = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        body = f"{content}\n\n---\nSource: Telegram intake\nUpdate ID: {update_id}\nCaptured: {captured}"
        try:
            item_id = project.add_draft_issue(project_id, make_title(content), body)
        except Exception:
            write_cursor(cursor, cursor_path)
            raise
        status_id = option_id(fields.get("Status"), "Idea Inbox")
        type_id = option_id(fields.get("Type"), TYPE_OPTIONS[kind])
        for field, value_id, label in ((fields.get("Status"), status_id, "Status/Idea Inbox"),
                                       (fields.get("Type"), type_id, f"Type/{TYPE_OPTIONS[kind]}")):
            if not field or not value_id:
                log(f"Warning: could not resolve {label}; leaving it unset.")
                continue
            try:
                project.set_single_select(project_id, item_id, field["id"], value_id)
            except Exception:
                log(f"Warning: could not set {label}; leaving it unset.")
        # The item exists, so this update is done. Persist that before anything
        # else can fail: a lost confirmation costs a duplicate, a lost cursor
        # costs a duplicate of every item created in this batch.
        mark_processed(cursor, update_id)
        write_cursor(cursor, cursor_path)
        if isinstance(chat_id, int):
            try:
                telegram.send_message(chat_id, f"Captured as {kind}.")
            except Exception:
                log("Warning: capture succeeded but the confirmation reply failed.")


def main() -> int:
    try:
        telegram = TelegramClient(required("TELEGRAM_INTAKE_BOT_TOKEN"))
        owner_id = required_integer("OWNER_TELEGRAM_ID")
        project = ProjectClient(required("PROJECT_TOKEN"), os.environ.get("PROJECT_OWNER", "pavelmetalarm"),
                                int(os.environ.get("PROJECT_NUMBER", "8")))
    except Exception as exc:
        # Only configuration errors are safe to echo: API responses can contain private content.
        log(str(exc))
        return 1
    try:
        run(telegram, project, owner_id)
    except Exception as exc:
        # API-level failures carry provider error text, never message content.
        log(f"Poll failed; cursor was not advanced past the failed update. Cause: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
