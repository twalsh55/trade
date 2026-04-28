from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.adapters.notifications.telegram_setup import (
    TelegramSetupError,
    extract_chat_ids,
    fetch_updates,
    format_chat_id_report,
    get_env_secret,
)
from src.env_utils import load_env_file


def main() -> int:
    load_env_file()
    bot_token = get_env_secret("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Missing TELEGRAM_BOT_TOKEN. Add it to .env first.")
        return 1

    try:
        payload = fetch_updates(bot_token)
    except TelegramSetupError as exc:
        print(str(exc))
        return 1

    print(format_chat_id_report(extract_chat_ids(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
