"""Load Handshake / browser cookie exports for Cloudflare Browser Rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_cookies_file(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array of cookies, or an object with a ``cookies`` key (browser export)."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array of cookies, got {type(data).__name__}")
    out: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Cookie at index {i} must be an object")
        if "name" not in item or "value" not in item:
            raise ValueError(f"Cookie at index {i} must include 'name' and 'value'")
        out.append(item)
    return out
