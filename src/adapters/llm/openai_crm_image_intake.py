from __future__ import annotations

import csv
import io
import json
from base64 import b64encode

import httpx


class OpenAICRMImageIntakeError(RuntimeError):
    """Raised when AI note image intake fails."""


class OpenAICRMImageIntakeAgent:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        timeout_seconds: float = 45.0,
        max_output_tokens: int = 1200,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def extract_spreadsheet_rows_from_image(
        self,
        prompt: str,
        preferred_formats: list[str],
        file_name: str,
        file_bytes: bytes,
    ) -> str:
        if not file_bytes:
            raise OpenAICRMImageIntakeError("Image file content is required.")

        instructions = (
            "You extract CRM follow-up rows from screenshots or photos of notes. "
            "Return JSON only in the form "
            '{"rows":[{"lead_name":"","company_name":"","owner_name":"","stage":"","next_follow_up_at":"","notes":"","priority":"","contact_channel":"","next_step":""}]}. '
            "Use empty strings for unknown values. "
            "Prefer one row per contact or company that clearly appears in the image. "
            "Preserve uncertainty in notes rather than inventing facts. "
            "If no CRM-relevant information is present, return {\"rows\":[]}. "
            f"User-specific intake prompt: {prompt.strip() or 'Focus on extracting follow-up-critical CRM fields.'} "
            f"User's common formats: {', '.join(preferred_formats) if preferred_formats else 'not provided'}."
        )
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Interpret this note image for CRM import. File name: {file_name}.",
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{_detect_mime_type(file_name)};base64,{b64encode(file_bytes).decode('ascii')}",
                        },
                    ],
                }
            ],
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenAICRMImageIntakeError("Unable to read this note image with AI right now.") from exc

        content = _extract_text_from_response(body)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAICRMImageIntakeError("AI image intake returned an invalid payload.") from exc

        rows = parsed.get("rows", [])
        if not isinstance(rows, list):
            raise OpenAICRMImageIntakeError("AI image intake returned an invalid payload.")
        if not rows:
            raise OpenAICRMImageIntakeError("No CRM-relevant notes were detected in this image.")
        return _rows_to_csv(rows)


def _detect_mime_type(file_name: str) -> str:
    normalized = file_name.strip().lower()
    if normalized.endswith(".png"):
        return "image/png"
    if normalized.endswith(".webp"):
        return "image/webp"
    if normalized.endswith(".jpg") or normalized.endswith(".jpeg"):
        return "image/jpeg"
    raise OpenAICRMImageIntakeError("Upload a supported image file: .png, .jpg, .jpeg, or .webp.")


def _extract_text_from_response(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = payload.get("output", [])
    if not isinstance(output, list):
        raise OpenAICRMImageIntakeError("AI image intake returned an invalid payload.")

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
        raise OpenAICRMImageIntakeError("AI image intake returned an invalid payload.")
    return content


def _rows_to_csv(rows: list[object]) -> str:
    fieldnames = [
        "lead_name",
        "company_name",
        "owner_name",
        "stage",
        "next_follow_up_at",
        "notes",
        "priority",
        "contact_channel",
        "next_step",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        if not isinstance(row, dict):
            continue
        writer.writerow({field: _normalize_cell(row.get(field)) for field in fieldnames})
    content = buffer.getvalue().strip()
    if content == ",".join(fieldnames):
        raise OpenAICRMImageIntakeError("No CRM-relevant notes were detected in this image.")
    return content + "\n"


def _normalize_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
