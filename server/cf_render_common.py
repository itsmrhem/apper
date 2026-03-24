"""Shared Cloudflare Browser Rendering request pieces (cookies, headers, goto)."""

import json
from pathlib import Path
from typing import Any

from cloudflare import NOT_GIVEN

from server.config import Settings
from server.cookies import load_cookies_file
from server.state import GraphState

# Cloudflare goto_options.timeout max is 60000 ms; networkidle0 often never fires on SPAs (e.g. Handshake).
_GOTO_TIMEOUT_MAX_MS = 60_000.0


def goto_options_for_sdk(raw: dict[str, Any] | None) -> Any:
    if not raw:
        return NOT_GIVEN
    out: dict[str, Any] = {}
    if "wait_until" in raw:
        out["wait_until"] = raw["wait_until"]
    elif "waitUntil" in raw:
        out["wait_until"] = raw["waitUntil"]
    if "timeout" in raw and raw["timeout"] is not None:
        out["timeout"] = min(float(raw["timeout"]), _GOTO_TIMEOUT_MAX_MS)
    if "referer" in raw:
        out["referer"] = raw["referer"]
    elif "referrer" in raw:
        out["referer"] = raw["referrer"]
    if not out:
        return NOT_GIVEN
    out.setdefault("wait_until", "load")
    out.setdefault("timeout", _GOTO_TIMEOUT_MAX_MS)
    return out


def extra_headers_for_sdk(
    state: GraphState,
    settings: Settings,
    *,
    use_cookie_header: bool,
) -> Any:
    headers = dict(state.get("extra_http_headers") or {})
    if (
        use_cookie_header
        and settings.handshake_cookie
        and "Cookie" not in headers
        and "cookie" not in headers
    ):
        headers["Cookie"] = settings.handshake_cookie
    return headers if headers else NOT_GIVEN


def resolve_cookies(state: GraphState, settings: Settings) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Returns (cookies_for_api, error_message)."""
    direct = state.get("cookies")
    if direct is not None:
        if not isinstance(direct, list):
            return None, "State `cookies` must be a list of objects with name/value."
        for i, item in enumerate(direct):
            if not isinstance(item, dict) or "name" not in item or "value" not in item:
                return None, f"State `cookies[{i}]` must be an object with name and value."
        return direct, None

    path_str = (state.get("cookies_path") or "").strip() or (settings.handshake_cookies_path or "").strip()
    if not path_str:
        return None, None
    path = Path(path_str).expanduser()
    if not path.is_file():
        return None, f"Cookie file not found: {path}"
    try:
        return load_cookies_file(path), None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"Invalid cookie file {path}: {exc}"
