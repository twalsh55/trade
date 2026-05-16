from __future__ import annotations

import time

from src.adapters.notifications.smtp_email_notifier import EmailNotificationError
from src.adapters.prospecting.runtime import parse_positive_int, run_prospecting_job
from src.adapters.social.reddit_lead_source import RedditLeadSourceError
from src.env_utils import load_env_file


def main() -> int:
    load_env_file()
    interval_minutes = parse_positive_int("PROSPECT_PERIODIC_INTERVAL_MINUTES", default=1440)
    max_runs = parse_positive_int("PROSPECT_PERIODIC_MAX_RUNS", default=1)

    for index in range(1, max_runs + 1):
        try:
            digest = run_prospecting_job()
        except ValueError as exc:
            print(str(exc))
            return 1
        except (EmailNotificationError, RedditLeadSourceError, RuntimeError) as exc:
            print(str(exc))
            return 1

        print(
            f"Run {index}/{max_runs}: profile={digest.profile} scanned={digest.scanned_post_count} "
            f"shortlisted={digest.shortlisted_count} token_usage={_format_token_usage(digest)}"
        )
        if index < max_runs:
            time.sleep(interval_minutes * 60)
    return 0


def _format_token_usage(digest) -> str:  # type: ignore[no-untyped-def]
    usage = getattr(digest, "token_usage", None)
    if usage is None:
        return "template-mode"
    return f"{usage.total_tokens} total ({usage.input_tokens} in / {usage.output_tokens} out) via {usage.model}"


if __name__ == "__main__":
    raise SystemExit(main())
