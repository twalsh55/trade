from __future__ import annotations

from datetime import UTC, datetime

from src.adapters.notifications.smtp_email_notifier import EmailNotificationError
from src.adapters.prospecting.runtime import (
    build_config_from_env,
    build_drafter_from_env,
    build_digest_delivery_from_env,
    build_email_notifier_from_env,
    get_app_openai_api_key,
    build_lead_source_from_env,
    build_usage_log_from_env,
    build_telegram_digest_notifier_from_env,
    collect_prospecting_config_errors,
    has_configured_smtp_delivery,
    has_configured_telegram_delivery,
    is_placeholder_openai_key,
    parse_positive_int,
    required_env,
    run_prospecting_job,
)


def test_build_config_from_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PROSPECT_REDDIT_SEARCH_TERMS", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("PROSPECT_PROFILE", raising=False)

    config = build_config_from_env()

    assert config.recipient_email == "tom.mg.walsh@gmail.com"
    assert config.search_terms
    assert config.app_url is None
    assert config.profile == "general"


def test_build_config_from_env_uses_crm_profile_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PROSPECT_REDDIT_SEARCH_TERMS", raising=False)
    monkeypatch.setenv("PROSPECT_PROFILE", "crm_direction")

    config = build_config_from_env()

    assert config.profile == "crm_direction"
    assert "lead follow up manually" in config.search_terms
    assert "CRM product" in config.app_summary


def test_build_config_from_env_appends_founder_guidance(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_PROFILE", "crm_direction")

    config = build_config_from_env("fix a bug with login")

    assert "Founder guidance: fix a bug with login." in config.app_summary


def test_build_email_notifier_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)

    try:
        build_email_notifier_from_env()
    except ValueError as exc:
        assert str(exc) == "Missing SMTP_HOST. Add it to .env first."
    else:
        raise AssertionError("Expected ValueError")


def test_build_email_notifier_from_env_builds_configured_notifier(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USE_TLS", "false")

    notifier = build_email_notifier_from_env()

    assert notifier.host == "smtp.example.com"
    assert notifier.port == 2525
    assert notifier.username == "mailer"
    assert notifier.from_email == "alerts@example.com"
    assert notifier.use_tls is False


def test_build_drafter_from_env_uses_template_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_drafter_from_env().__class__.__name__ == "TemplateProspectDrafter"


def test_build_drafter_from_env_uses_openai_when_api_key_present(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-test-realistic-key-1234567890")
    drafter = build_drafter_from_env()
    assert drafter.__class__.__name__ == "OpenAIProspectDrafter"
    assert drafter.model == "gpt-5.4"


def test_build_drafter_from_env_uses_template_for_placeholder_api_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-...")
    assert build_drafter_from_env().__class__.__name__ == "TemplateProspectDrafter"
    assert is_placeholder_openai_key("sk-...") is True
    assert is_placeholder_openai_key("your-openai-api-key") is True
    assert is_placeholder_openai_key("sk-test-realistic-key-1234567890") is False


def test_get_app_openai_api_key_prefers_app_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_OPENAI_API_KEY", "app-key")
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    assert get_app_openai_api_key() == "app-key"


def test_build_lead_source_from_env_uses_custom_user_agent(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_REDDIT_USER_AGENT", "custom-agent")
    monkeypatch.setenv("PROSPECT_PUBLIC_SEARCH_USER_AGENT", "public-agent")
    source = build_lead_source_from_env()
    assert source.__class__.__name__ == "CompositeLeadSource"
    assert source.sources[0].user_agent == "custom-agent"
    assert source.sources[1].__class__.__name__ == "HackerNewsLeadSource"
    assert source.sources[2].__class__.__name__ == "WebLeadSource"
    assert source.sources[2].search.user_agent == "public-agent"
    assert source.sources[3].__class__.__name__ == "IndieHackersLeadSource"
    assert source.sources[4].__class__.__name__ == "ReviewSiteLeadSource"
    assert source.sources[5].__class__.__name__ == "XLeadSource"
    assert source.sources[5].user_agent == "public-agent"
    assert source.sources[6].__class__.__name__ == "DiscordLeadSource"


def test_build_lead_source_from_env_respects_toggles(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_ENABLE_REDDIT_SOURCE", "false")
    monkeypatch.setenv("PROSPECT_ENABLE_HACKER_NEWS_SOURCE", "false")
    monkeypatch.setenv("PROSPECT_ENABLE_WEB_SOURCE", "false")
    monkeypatch.setenv("PROSPECT_ENABLE_INDIE_HACKERS_SOURCE", "false")
    monkeypatch.setenv("PROSPECT_ENABLE_REVIEW_SOURCE", "false")
    monkeypatch.setenv("PROSPECT_ENABLE_X_SOURCE", "true")
    monkeypatch.setenv("PROSPECT_ENABLE_DISCORD_SOURCE", "false")

    source = build_lead_source_from_env()

    assert [item.__class__.__name__ for item in source.sources] == ["XLeadSource"]


def test_build_telegram_digest_notifier_from_env_requires_telegram(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    try:
        build_telegram_digest_notifier_from_env()
    except ValueError as exc:
        assert str(exc) == "Missing TELEGRAM_BOT_TOKEN. Add it to .env first."
    else:
        raise AssertionError("Expected ValueError")


def test_build_digest_delivery_from_env_uses_telegram_when_only_telegram_is_configured(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    fallback = build_digest_delivery_from_env()
    assert fallback.__class__.__name__ == "TelegramDigestNotifier"


def test_build_digest_delivery_from_env_uses_smtp_when_only_smtp_is_configured(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    smtp = build_digest_delivery_from_env()
    assert smtp.__class__.__name__ == "SMTPEmailNotifier"


def test_build_digest_delivery_from_env_uses_both_channels_when_both_are_configured(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")

    delivery = build_digest_delivery_from_env()

    assert delivery.__class__.__name__ == "CompositeEmailNotifier"


def test_build_digest_delivery_from_env_requires_at_least_one_channel(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)

    try:
        build_digest_delivery_from_env()
    except ValueError as exc:
        assert str(exc) == "Missing SMTP delivery settings and Telegram delivery fallback is unavailable."
    else:
        raise AssertionError("Expected ValueError")


def test_collect_prospecting_config_errors_reports_missing_and_invalid_fields(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_OPENAI_API_KEY", "sk-...")
    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "abc")
    monkeypatch.setenv("PROSPECT_PERIODIC_INTERVAL_MINUTES", "bad")
    monkeypatch.setenv("SMTP_PORT", "0")

    errors = collect_prospecting_config_errors()

    assert "App OpenAI key looks like a placeholder. Set APP_OPENAI_API_KEY or a real OPENAI_API_KEY." in errors
    assert "Missing SMTP delivery settings and Telegram delivery fallback is unavailable" in errors
    assert "PROSPECT_MAX_MATCHES must be an integer" in errors
    assert "PROSPECT_PERIODIC_INTERVAL_MINUTES must be an integer" in errors
    assert "SMTP_PORT must be greater than zero" in errors


def test_collect_prospecting_config_errors_allows_telegram_fallback(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("APP_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    assert collect_prospecting_config_errors() == []


def test_required_env_and_parse_positive_int(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "4")

    assert required_env("SMTP_HOST") == "smtp.example.com"
    assert parse_positive_int("PROSPECT_MAX_MATCHES", default=3) == 4


def test_delivery_configuration_helpers(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert has_configured_smtp_delivery() is False
    assert has_configured_telegram_delivery() is False

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    assert has_configured_telegram_delivery() is True

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    assert has_configured_smtp_delivery() is True


def test_parse_positive_int_raises_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "0")

    try:
        parse_positive_int("PROSPECT_MAX_MATCHES", default=3)
    except ValueError as exc:
        assert str(exc) == "PROSPECT_MAX_MATCHES must be greater than zero."
    else:
        raise AssertionError("Expected ValueError")

    monkeypatch.setenv("PROSPECT_MAX_MATCHES", "abc")
    try:
        parse_positive_int("PROSPECT_MAX_MATCHES", default=3)
    except ValueError as exc:
        assert str(exc) == "PROSPECT_MAX_MATCHES must be an integer."
    else:
        raise AssertionError("Expected ValueError")


def test_run_prospecting_job_builds_and_executes_use_case(monkeypatch) -> None:
    config = object()
    lead_source = object()
    drafter = object()
    email_delivery = object()
    digest = type(
        "Digest",
        (),
        {
            "generated_at": datetime(2026, 5, 14, tzinfo=UTC),
            "profile": "general",
            "scanned_post_count": 3,
            "shortlisted_count": 1,
            "shortlisted_posts": (),
            "token_usage": None,
        },
    )()
    seen_guidance: list[str | None] = []
    monkeypatch.setattr(
        "src.adapters.prospecting.runtime.build_config_from_env",
        lambda founder_guidance=None: seen_guidance.append(founder_guidance) or config,
    )
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_lead_source_from_env", lambda: lead_source)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_drafter_from_env", lambda: drafter)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_digest_delivery_from_env", lambda: email_delivery)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_usage_log_from_env", lambda: None)
    monkeypatch.setattr("src.adapters.prospecting.runtime._queue_agent_build_recommendation_if_enabled", lambda digest, founder_guidance=None: None)
    briefing_triggers: list[str] = []
    monkeypatch.setattr("src.adapters.prospecting.runtime.run_operator_briefing_job", lambda trigger_label="scheduled update": briefing_triggers.append(trigger_label))

    class FakeUseCase:
        def __init__(self, lead_source, drafter, email_delivery) -> None:  # type: ignore[no-untyped-def]
            self.lead_source = lead_source
            self.drafter = drafter
            self.email_delivery = email_delivery

        def execute(self, passed_config):  # type: ignore[no-untyped-def]
            assert passed_config is config
            assert self.lead_source is lead_source
            assert self.drafter is drafter
            assert self.email_delivery is email_delivery
            return digest

    monkeypatch.setattr("src.adapters.prospecting.runtime.RunDailyProspectingUseCase", FakeUseCase)

    assert run_prospecting_job("fix login") is digest
    assert seen_guidance == ["fix login"]
    assert briefing_triggers == ["prospect run"]


def test_run_prospecting_job_appends_usage_log_when_configured(monkeypatch) -> None:
    config = object()
    digest = type(
        "Digest",
        (),
        {
            "generated_at": datetime(2026, 5, 14, tzinfo=UTC),
            "profile": "crm_direction",
            "scanned_post_count": 5,
            "shortlisted_count": 2,
            "shortlisted_posts": (),
            "token_usage": None,
        },
    )()
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_config_from_env", lambda founder_guidance=None: config)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_lead_source_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_drafter_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_digest_delivery_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.run_operator_briefing_job", lambda trigger_label="scheduled update": None)
    monkeypatch.setattr("src.adapters.prospecting.runtime._queue_agent_build_recommendation_if_enabled", lambda digest, founder_guidance=None: None)

    class FakeUseCase:
        def __init__(self, lead_source, drafter, email_delivery) -> None:  # type: ignore[no-untyped-def]
            pass

        def execute(self, passed_config):  # type: ignore[no-untyped-def]
            assert passed_config is config
            return digest

    appended: list[object] = []

    class FakeUsageLog:
        def append(self, logged_digest) -> None:  # type: ignore[no-untyped-def]
            appended.append(logged_digest)

    monkeypatch.setattr("src.adapters.prospecting.runtime.RunDailyProspectingUseCase", FakeUseCase)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_usage_log_from_env", lambda: FakeUsageLog())

    assert run_prospecting_job() is digest
    assert appended == [digest]


def test_run_prospecting_job_can_disable_operator_briefing(monkeypatch) -> None:
    config = object()
    digest = type(
        "Digest",
        (),
        {
            "generated_at": datetime(2026, 5, 14, tzinfo=UTC),
            "profile": "crm_direction",
            "scanned_post_count": 5,
            "shortlisted_count": 2,
            "shortlisted_posts": (),
            "token_usage": None,
        },
    )()
    monkeypatch.setenv("PROSPECT_SEND_OPERATOR_BRIEFING", "false")
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_config_from_env", lambda founder_guidance=None: config)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_lead_source_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_drafter_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_digest_delivery_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_usage_log_from_env", lambda: None)
    monkeypatch.setattr("src.adapters.prospecting.runtime._queue_agent_build_recommendation_if_enabled", lambda digest, founder_guidance=None: None)
    briefing_triggers: list[str] = []
    monkeypatch.setattr("src.adapters.prospecting.runtime.run_operator_briefing_job", lambda trigger_label="scheduled update": briefing_triggers.append(trigger_label))

    class FakeUseCase:
        def __init__(self, lead_source, drafter, email_delivery) -> None:  # type: ignore[no-untyped-def]
            pass

        def execute(self, passed_config):  # type: ignore[no-untyped-def]
            assert passed_config is config
            return digest

    monkeypatch.setattr("src.adapters.prospecting.runtime.RunDailyProspectingUseCase", FakeUseCase)

    assert run_prospecting_job() is digest
    assert briefing_triggers == []


def test_run_prospecting_job_tolerates_operator_briefing_email_failure(monkeypatch) -> None:
    config = object()
    digest = type(
        "Digest",
        (),
        {
            "generated_at": datetime(2026, 5, 14, tzinfo=UTC),
            "profile": "crm_direction",
            "scanned_post_count": 5,
            "shortlisted_count": 2,
            "shortlisted_posts": (),
            "token_usage": None,
        },
    )()
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_config_from_env", lambda founder_guidance=None: config)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_lead_source_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_drafter_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_digest_delivery_from_env", lambda: object())
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_usage_log_from_env", lambda: None)
    monkeypatch.setattr("src.adapters.prospecting.runtime._queue_agent_build_recommendation_if_enabled", lambda digest, founder_guidance=None: None)
    monkeypatch.setattr(
        "src.adapters.prospecting.runtime.run_operator_briefing_job",
        lambda trigger_label="scheduled update": (_ for _ in ()).throw(EmailNotificationError("smtp down")),
    )

    class FakeUseCase:
        def __init__(self, lead_source, drafter, email_delivery) -> None:  # type: ignore[no-untyped-def]
            pass

        def execute(self, passed_config):  # type: ignore[no-untyped-def]
            assert passed_config is config
            return digest

    monkeypatch.setattr("src.adapters.prospecting.runtime.RunDailyProspectingUseCase", FakeUseCase)

    assert run_prospecting_job() is digest


def test_queue_agent_build_recommendation_enqueues_strong_recommendation(monkeypatch) -> None:
    digest = object()
    created: list[tuple[str, str, str | None]] = []
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class FakeRepository:
        def create_request(self, source_chat_id: str, command_text: str, guidance: str | None, created_at: datetime):
            created.append((source_chat_id, command_text, guidance))
            return object()

    brief = type(
        "Brief",
        (),
        {
            "should_build": True,
            "feature_name": "CSV and Google Sheets import",
        },
    )()
    monkeypatch.setattr("src.adapters.prospecting.runtime.decide_autonomous_build_brief", lambda passed_digest: brief)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_founder_code_request_repository", lambda: FakeRepository())
    monkeypatch.setattr("src.adapters.prospecting.runtime.format_autonomous_build_brief", lambda passed_brief: "build now")

    from src.adapters.prospecting.runtime import _queue_agent_build_recommendation_if_enabled

    _queue_agent_build_recommendation_if_enabled(digest, founder_guidance=None)

    assert created == [("agent:prospect", "/agent CSV and Google Sheets import", "build now")]


def test_queue_agent_build_recommendation_skips_guided_or_hold_runs(monkeypatch) -> None:
    digest = object()
    called: list[str] = []
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    brief = type(
        "Brief",
        (),
        {
            "should_build": False,
            "feature_name": None,
        },
    )()
    monkeypatch.setattr("src.adapters.prospecting.runtime.decide_autonomous_build_brief", lambda passed_digest: called.append("brief") or brief)
    monkeypatch.setattr("src.adapters.prospecting.runtime.build_founder_code_request_repository", lambda: (_ for _ in ()).throw(AssertionError("should not build repository")))

    from src.adapters.prospecting.runtime import _queue_agent_build_recommendation_if_enabled

    _queue_agent_build_recommendation_if_enabled(digest, founder_guidance="fix login")
    assert called == []

    _queue_agent_build_recommendation_if_enabled(digest, founder_guidance=None)
    assert called == ["brief"]


def test_queue_agent_build_recommendation_tolerates_queue_failure(monkeypatch) -> None:
    digest = object()
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    brief = type(
        "Brief",
        (),
        {
            "should_build": True,
            "feature_name": "Inbox and DM capture",
        },
    )()
    monkeypatch.setattr("src.adapters.prospecting.runtime.decide_autonomous_build_brief", lambda passed_digest: brief)
    monkeypatch.setattr(
        "src.adapters.prospecting.runtime.build_founder_code_request_repository",
        lambda: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr("src.adapters.prospecting.runtime.format_autonomous_build_brief", lambda passed_brief: "build now")

    from src.adapters.prospecting.runtime import _queue_agent_build_recommendation_if_enabled

    _queue_agent_build_recommendation_if_enabled(digest, founder_guidance=None)


def test_queue_agent_build_recommendation_skips_without_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "src.adapters.prospecting.runtime.decide_autonomous_build_brief",
        lambda passed_digest: (_ for _ in ()).throw(AssertionError("should not decide without a durable queue")),
    )

    from src.adapters.prospecting.runtime import _queue_agent_build_recommendation_if_enabled

    _queue_agent_build_recommendation_if_enabled(object(), founder_guidance=None)


def test_queue_agent_build_recommendation_respects_disable_toggle(monkeypatch) -> None:
    monkeypatch.setenv("PROSPECT_QUEUE_AGENT_RECOMMENDATIONS", "false")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setattr(
        "src.adapters.prospecting.runtime.decide_autonomous_build_brief",
        lambda passed_digest: (_ for _ in ()).throw(AssertionError("should not decide when disabled")),
    )

    from src.adapters.prospecting.runtime import _queue_agent_build_recommendation_if_enabled

    _queue_agent_build_recommendation_if_enabled(object(), founder_guidance=None)


def test_build_usage_log_from_env_respects_toggle_and_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROSPECT_USAGE_LOG_FILE", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("PROSPECT_TRACK_USAGE", "true")
    usage_log = build_usage_log_from_env()
    assert usage_log is not None
    assert usage_log.path == tmp_path / "usage.jsonl"

    monkeypatch.setenv("PROSPECT_TRACK_USAGE", "false")
    assert build_usage_log_from_env() is None
