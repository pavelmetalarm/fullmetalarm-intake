"""Alert the owner about Telegram updates the poller has not yet consumed."""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intake.poll import CURSOR_PATH, read_cursor, required, required_integer
from intake.telegram import TelegramClient


def run(telegram: TelegramClient, owner_id: int, stale_hours: float, now: dt.datetime | None = None) -> None:
    cursor = read_cursor(CURSOR_PATH)
    updates = telegram.get_updates(cursor["offset"])
    dated = [u.get("message", {}).get("date") for u in updates if isinstance(u.get("message"), dict)]
    dates = [date for date in dated if isinstance(date, int)]
    if not dates:
        return
    current = now or dt.datetime.now(dt.timezone.utc)
    oldest = dt.datetime.fromtimestamp(min(dates), tz=dt.timezone.utc)
    age_hours = max(0, (current - oldest).total_seconds() / 3600)
    if age_hours >= stale_hours:
        telegram.send_message(owner_id, f"Telegram intake has {len(updates)} pending updates; oldest is {age_hours:.1f} hours old.")


def main() -> int:
    try:
        token = required("TELEGRAM_INTAKE_BOT_TOKEN")
        owner_id = required_integer("OWNER_TELEGRAM_ID")
        stale_hours = float(os.environ.get("STALE_HOURS", "6"))
        run(TelegramClient(token), owner_id, stale_hours)
    except Exception:
        # A watchdog must not make a scheduler failure noisier than the missed intake itself.
        print("Watchdog warning: check could not be completed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
