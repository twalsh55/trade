from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.notifications.telegram_notifier import TelegramNotificationError, TelegramNotifier
from src.adapters.notifications.telegram_setup import get_env_secret
from src.config.env import load_env_file


def main() -> int:
    load_env_file()
    bot_token = get_env_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_env_secret("TELEGRAM_CHAT_ID")
    if not bot_token:
        print("Missing TELEGRAM_BOT_TOKEN. Add it to .env first.")
        return 1
    if not chat_id:
        print("Missing TELEGRAM_CHAT_ID. Add it to .env first.")
        return 1

    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
    try:
        notifier.send_message("Telegram test message from Market Crash Monitor.")
    except TelegramNotificationError as exc:
        print(str(exc))
        return 1

    print("Telegram test message sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
