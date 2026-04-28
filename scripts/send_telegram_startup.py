from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.notifications.telegram_notifier import TelegramNotificationError, TelegramNotifier
from src.adapters.notifications.telegram_setup import get_env_secret
from src.env_utils import load_env_file


def build_startup_message(refreshed_at: datetime) -> str:
    timezone = ZoneInfo(get_env_secret("APP_TIMEZONE") or "Europe/Rome")
    local_time = refreshed_at.astimezone(timezone).strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        "Market Crash Monitor server started\n"
        f"Startup time: {local_time}"
    )


def main() -> int:
    load_env_file()
    bot_token = get_env_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_env_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("Skipping Telegram startup message: missing bot token or chat ID.")
        return 0

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    try:
        notifier.send_message(build_startup_message(datetime.now().astimezone()))
    except TelegramNotificationError as exc:
        print(str(exc))
        return 1

    print("Telegram startup message sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
