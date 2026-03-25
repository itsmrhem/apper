"""Send job titles and summaries to Telegram after /json extraction."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from server.config import get_settings
from server.state import GraphState

_TELEGRAM_MAX = 4096
# Leave headroom below API limit for safety
_CHUNK_TARGET = 3800


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _extract_title_summary(row: dict[str, Any]) -> tuple[str, str, str]:
    ex = row.get("extracted") if isinstance(row.get("extracted"), dict) else {}
    title = str(ex.get("title") or "").strip() or "(no title)"
    title = _clip(title, 200)
    summary = str(ex.get("summary") or "").strip()
    if not summary:
        jd = str(ex.get("job_description") or "").strip()
        summary = _clip(jd, 900) if jd else "(no summary)"
    else:
        summary = _clip(summary, 1200)
    url = str(row.get("url") or "").strip()
    return title, summary, url


def _pack_messages(rows: list[dict[str, Any]]) -> list[str]:
    """Split into Telegram-sized messages."""
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("error"):
            continue
        title, summary, url = _extract_title_summary(row)
        n = len(parts) + 1
        parts.append(f"{n}. {title}\n{summary}\n{url}\n")
    if not parts:
        return ["Job details: no successful extractions to show."]
    header = f"Job listings ({len(parts)})\n\n"
    out: list[str] = []
    cur = header
    for p in parts:
        sep = "" if cur == header else "—\n"
        nxt = cur + sep + p
        if len(nxt) <= _CHUNK_TARGET:
            cur = nxt
        else:
            if cur != header:
                out.append(cur[:_TELEGRAM_MAX])
            cur = header + p
    if cur != header:
        out.append(cur[:_TELEGRAM_MAX])
    return out


async def telegram_job_listing_node(state: GraphState) -> dict[str, Any]:
    settings = get_settings()
    token = (settings.telegram_bot_token or "").strip()
    chat = (settings.telegram_chat_id or "").strip()
    if not token or not chat:
        return {"telegram_job_listing_error": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing."}

    rows = state.get("job_details") or []
    if not isinstance(rows, list) or not rows:
        return {"telegram_job_listing_error": None, "telegram_job_listing_sent_count": 0}

    texts = _pack_messages(rows)
    if not texts:
        return {"telegram_job_listing_error": None, "telegram_job_listing_sent_count": 0}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for t in texts:
                r = await client.post(url, json={"chat_id": chat, "text": t})
                r.raise_for_status()
                sent += 1
                await asyncio.sleep(0.35)
    except (httpx.HTTPError, OSError) as exc:
        # Non-fatal: report the failure but keep graph moving.
        return {
            "telegram_job_listing_error": f"Telegram send failed: {exc}",
            "telegram_job_listing_sent_count": sent,
        }

    return {"telegram_job_listing_error": None, "telegram_job_listing_sent_count": sent}
