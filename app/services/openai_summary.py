from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings

OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_URL = "https://api.openai.com/v1/responses"

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "keyPoints": {
            "type": "array",
            "items": {"type": "string"},
        },
        "notesDigest": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "keyPoints", "notesDigest"],
}

INSTRUCTIONS = """너는 사용자의 독서 기록을 정리해주는 독서 어시스턴트다.
책의 원래 줄거리나 저자의 의도를 단정해서 쓰지 말고, 반드시 사용자가 남긴 메모와 기록만 바탕으로 요약하라.
정보가 부족하면 과장하거나 추측하지 말고, 메모에서 드러나는 인상과 관심사를 중심으로 정리하라.
출력은 반드시 JSON으로만 반환하라."""


def build_summary_prompt(payload: dict[str, Any]) -> str:
    return (
        "다음 독서 기록을 바탕으로 사용자의 독서 흔적을 요약하라.\n\n"
        "요구사항:\n"
        "- summary는 2~4문장으로 작성한다.\n"
        "- summary는 책 줄거리 요약이 아니라 사용자가 주목한 주제, 감정, 인상 중심으로 작성한다.\n"
        "- keyPoints는 2~4개 작성한다.\n"
        "- notesDigest는 사용자의 메모를 짧게 정리한 문장 2~4개로 작성한다.\n"
        "- 메모 원문이 부족하면 없는 내용을 상상하지 말고 보수적으로 작성한다.\n"
        "- \"저자는 ~를 말한다\"처럼 단정하지 말고, \"남겨주신 메모를 보면\", \"특히 주목한 부분은\" 같은 표현을 사용한다.\n"
        "- 한국어로 작성한다.\n\n"
        "독서 기록 데이터:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _extract_output_text(response_json: dict[str, Any]) -> str:
    output = response_json.get("output") or []
    texts: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])
    if texts:
        return "\n".join(texts)
    raise ValueError("OpenAI response did not include output_text")


def generate_reading_summary(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    body = {
        "model": OPENAI_MODEL,
        "instructions": INSTRUCTIONS,
        "input": build_summary_prompt(payload),
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "reading_summary",
                "strict": True,
                "schema": SUMMARY_SCHEMA,
            }
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.post(OPENAI_URL, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    text = _extract_output_text(data)
    parsed = json.loads(text)
    return {
        "summary": parsed.get("summary") or "",
        "keyPoints": parsed.get("keyPoints") or [],
        "notesDigest": parsed.get("notesDigest") or [],
        "model": OPENAI_MODEL,
    }
