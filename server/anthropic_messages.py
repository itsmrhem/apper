"""Minimal async Anthropic Messages API client."""

from __future__ import annotations

import json
from typing import Any

import httpx


async def anthropic_text_completion(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 16_384,
    timeout: float = 300.0,
) -> str:
    if not api_key.strip():
        raise ValueError("Anthropic API key is empty.")
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key.strip(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model.strip(),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, content=json.dumps(body))
        resp.raise_for_status()
        data = resp.json()
    blocks = data.get("content") or []
    texts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            t = b.get("text")
            if isinstance(t, str):
                texts.append(t)
    return "".join(texts).strip()


def strip_latex_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t
