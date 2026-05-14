from __future__ import annotations

import json

import httpx

from src.domain.prospecting import ProspectMatch


class OpenAIProspectDrafterError(RuntimeError):
    """Raised when promotional reply drafting fails."""


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

    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[str]:
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
            "You are helping with low-volume outbound research for a SaaS app. "
            "For each post, write one concise, helpful promotional reply under 70 words. "
            "Do not claim you already use the product. Do not be pushy. "
            "Return JSON only in the form "
            '{"drafts":[{"post_id":"...","reply":"..."}]}.'
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
            raise OpenAIProspectDrafterError("Unable to generate promotional drafts.") from exc

        content = _extract_text_from_response(payload)
        try:
            response_json = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAIProspectDrafterError("OpenAI returned an invalid drafting payload.") from exc

        drafts = response_json.get("drafts", [])
        if not isinstance(drafts, list):
            raise OpenAIProspectDrafterError("OpenAI returned an invalid drafting payload.")

        replies_by_id: dict[str, str] = {}
        for item in drafts:
            if not isinstance(item, dict):
                continue
            post_id = item.get("post_id")
            reply = item.get("reply")
            if isinstance(post_id, str) and isinstance(reply, str):
                replies_by_id[post_id] = reply.strip()

        return [
            replies_by_id.get(match.post.external_id) or _build_template_reply(match.post.title, app_url)
            for match in matches
        ]


class TemplateProspectDrafter:
    def draft_promotional_replies(
        self,
        app_summary: str,
        matches: tuple[ProspectMatch, ...],
        app_url: str | None = None,
    ) -> list[str]:
        return [_build_template_reply(match.post.title, app_url) for match in matches]


def _build_template_reply(post_title: str, app_url: str | None) -> str:
    app_link = f" You can check it here: {app_url}" if app_url else ""
    return (
        f"If you're comparing tools for this kind of workflow, I built a small app focused on "
        f"crash-risk monitoring and investor alerts. It may be useful for the problem behind "
        f"'{post_title}'. Happy to share it if that would help.{app_link}"
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
