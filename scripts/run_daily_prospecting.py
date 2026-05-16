from __future__ import annotations

from src.adapters.notifications.smtp_email_notifier import EmailNotificationError
from src.adapters.prospecting.runtime import (
    build_config_from_env,
    build_drafter_from_env,
    build_email_notifier_from_env,
    run_prospecting_job,
)
from src.adapters.social.reddit_lead_source import RedditLeadSourceError
from src.env_utils import load_env_file


def main() -> int:
    load_env_file()
    try:
        config = build_config_from_env()
        digest = run_prospecting_job()
    except ValueError as exc:
        print(str(exc))
        return 1
    except (EmailNotificationError, RedditLeadSourceError) as exc:
        print(str(exc))
        return 1

    print(
        f"Prospecting digest emailed to {config.recipient_email}. "
        f"Scanned {digest.scanned_post_count} posts and shortlisted {digest.shortlisted_count}. "
        f"Profile={digest.profile}. "
        f"Token usage={_format_token_usage(digest)}."
    )
    return 0


def _format_token_usage(digest) -> str:  # type: ignore[no-untyped-def]
    usage = getattr(digest, "token_usage", None)
    if usage is None:
        return "template-mode"
    return f"{usage.total_tokens} total ({usage.input_tokens} in / {usage.output_tokens} out) via {usage.model}"


if __name__ == "__main__":
    raise SystemExit(main())
