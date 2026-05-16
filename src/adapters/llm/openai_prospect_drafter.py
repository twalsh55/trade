from __future__ import annotations

import json

import httpx

from src.domain.prospecting import ProspectDraft, ProspectMatch, ProspectTokenUsage


class OpenAIProspectDrafterError(RuntimeError):
    """Raised when opportunity idea drafting fails."""


class OpenAIProspectDrafter:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5-nano",
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 500,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._last_usage: ProspectTokenUsage | None = None

    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[ProspectDraft]:
        self._last_usage = None
        if not matches:
            return []

        prompt_payload = {
            "app_summary": app_summary,
            "app_url": app_url,
            "posts": [
                {
                    "post_id": match.post.external_id,
                    "title": match.post.title,
                    "body_excerpt": match.post.body[:280],
                    "reasons": list(match.reasons),
                }
                for match in matches
            ],
        }
        instructions = (
            "You are helping with SaaS opportunity discovery for a solo founder. "
            "Be skeptical and avoid overfitting to keywords. "
            "If a post looks generic, hype-driven, launch-oriented, or only loosely related, do not invent a sophisticated idea from it. "
            "Stay close to explicit workflow pain, current workarounds, and operational consequences. "
            "Favor CRM-direction insights such as follow-up discipline, pipeline hygiene, relationship memory, handoffs, reminders, notes, and spreadsheet-held workflows. "
            "For each post, decide whether it is a strong signal, a weak signal, or should be rejected. "
            "Use reject when the evidence is mostly hype, product-launch noise, generic AI chatter, or weak keyword adjacency. "
            "For non-rejected posts, write one concise opportunity idea under 90 words describing a plausible SaaS product or feature, "
            "the workflow pain it addresses, and why it may be monetizable. "
            "Do not suggest posting, replying, outreach, or promotion. "
            "Return JSON only in the form "
            '{"drafts":[{"post_id":"...","idea":"...","assessment":"strong_signal|weak_signal|reject","confidence":"high|medium|low","noise_flags":["..."]}]}.'
        )

        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "instructions": instructions,
                    "input": json.dumps(prompt_payload),
                    "max_output_tokens": self.max_output_tokens,
                    "store": False,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenAIProspectDrafterError("Unable to generate opportunity ideas.") from exc

        self._last_usage = _extract_usage_from_response(payload, self.model)

        content = _extract_text_from_response(payload)
        try:
            response_json = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAIProspectDrafterError("OpenAI returned an invalid drafting payload.") from exc

        drafts = response_json.get("drafts", [])
        if not isinstance(drafts, list):
            raise OpenAIProspectDrafterError("OpenAI returned an invalid drafting payload.")

        replies_by_id: dict[str, ProspectDraft] = {}
        for item in drafts:
            if not isinstance(item, dict):
                continue
            post_id = item.get("post_id")
            reply = item.get("idea")
            if not isinstance(reply, str):
                reply = item.get("reply")
            assessment = item.get("assessment", "weak_signal")
            confidence = item.get("confidence", "medium")
            noise_flags = item.get("noise_flags", [])
            if not isinstance(assessment, str):
                assessment = "weak_signal"
            if not isinstance(confidence, str):
                confidence = "medium"
            if not isinstance(noise_flags, list):
                noise_flags = []
            normalized_noise_flags = tuple(flag.strip() for flag in noise_flags if isinstance(flag, str) and flag.strip())
            if isinstance(post_id, str) and isinstance(reply, str):
                replies_by_id[post_id] = ProspectDraft(
                    idea=reply.strip(),
                    assessment=assessment.strip().lower() or "weak_signal",
                    confidence=confidence.strip().lower() or "medium",
                    noise_flags=normalized_noise_flags,
                )
            elif isinstance(post_id, str):
                normalized_assessment = assessment.strip().lower() or "weak_signal"
                replies_by_id[post_id] = ProspectDraft(
                    idea="",
                    assessment="reject" if normalized_assessment == "reject" else normalized_assessment,
                    confidence=confidence.strip().lower() or "medium",
                    noise_flags=normalized_noise_flags or ("missing_idea",),
                )

        return [
            replies_by_id.get(match.post.external_id) or _build_model_omission_rejection()
            for match in matches
        ]

    def get_last_usage(self) -> ProspectTokenUsage | None:
        return self._last_usage


class TemplateProspectDrafter:
    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[ProspectDraft]:
        return [_build_template_reply(match.post.title, app_url) for match in matches]

    def get_last_usage(self) -> ProspectTokenUsage | None:
        return None


def _build_template_reply(post_title: str, app_url: str | None) -> ProspectDraft:
    app_link = f" Reference: {app_url}" if app_url else ""
    return ProspectDraft(
        idea=(
            f"Potential SaaS idea: build a lightweight workflow tool around the pain implied by "
            f"'{post_title}', with a focus on recurring admin reduction, clearer reporting, or better automation. "
            f"Prioritize narrow ROI, simple onboarding, and low-support execution.{app_link}"
        ),
        assessment="needs_review",
        confidence="low",
        noise_flags=("template_fallback",),
    )


def _build_model_omission_rejection() -> ProspectDraft:
    return ProspectDraft(
        idea="",
        assessment="reject",
        confidence="low",
        noise_flags=("model_omitted_item",),
    )


def _extract_text_from_response(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = payload.get("output", [])
    if not isinstance(output, list):
        raise OpenAIProspectDrafterError("OpenAI returned an invalid drafting payload.")

    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                parts.append(text)

    content = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not content:
        raise OpenAIProspectDrafterError("OpenAI returned an invalid drafting payload.")
    return content


def _extract_usage_from_response(payload: dict[str, object], model: str) -> ProspectTokenUsage | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)
    if not all(isinstance(value, int) for value in (input_tokens, output_tokens, total_tokens)):
        return None

    return ProspectTokenUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
