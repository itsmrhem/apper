"""Single LangGraph node: Cloudflare Browser Rendering via the official Python SDK."""

import json
from pathlib import Path
from typing import Any

from cloudflare import NOT_GIVEN, APIStatusError, AsyncCloudflare, CloudflareError

from server.config import Settings, get_settings
from server.cookies import load_cookies_file
from server.state import GraphState

# Cloudflare goto_options.timeout max is 60000 ms; networkidle0 often never fires on SPAs (e.g. Handshake).
_GOTO_TIMEOUT_MAX_MS = 60_000.0


def _goto_options_for_sdk(raw: dict[str, Any] | None) -> Any:
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


def _extra_headers(
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


def _resolve_cookies(state: GraphState, settings: Settings) -> tuple[list[dict[str, Any]] | None, str | None]:
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


async def browser_render_node(state: GraphState) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cf_account_id or not settings.cf_api_token:
        return {"error": "Set CF_ACCOUNT_ID and CF_API_TOKEN in the environment."}

    url = (state.get("url") or "").strip()
    if not url:
        return {"error": "State must include a non-empty `url`."}

    cookie_rows, cookie_err = _resolve_cookies(state, settings)
    if cookie_err:
        return {"error": cookie_err, "rendered_html": None, "cf_response": None}

    goto = _goto_options_for_sdk(state.get("goto_options"))
    extra_headers = _extra_headers(
        state,
        settings,
        use_cookie_header=not bool(cookie_rows),
    )
    cookies_arg = cookie_rows if cookie_rows else NOT_GIVEN

    best = state.get("best_attempt")
    if best is None:
        best = True
    action_timeout = state.get("action_timeout_ms")
    if action_timeout is None:
        action_timeout = 60_000.0

    try:
        async with AsyncCloudflare(api_token=settings.cf_api_token) as client:
            html = await client.browser_rendering.markdown.create(
                account_id=settings.cf_account_id,
                url=url,
                cookies=cookies_arg,
                set_extra_http_headers=extra_headers,
                goto_options=goto,
                best_attempt=best,
                action_timeout=action_timeout,
                timeout=180.0,
            )
    except APIStatusError as exc:
        body_preview = exc.body
        if body_preview is not None and not isinstance(body_preview, str):
            body_preview = str(body_preview)[:5000]
        elif isinstance(body_preview, str):
            body_preview = body_preview[:5000]
        return {
            "error": f"Cloudflare API HTTP {exc.status_code}: {exc.message}",
            "cf_response": {"body": body_preview},
            "rendered_html": None,
        }
    except CloudflareError as exc:
        return {
            "error": f"Cloudflare API error: {exc}",
            "cf_response": None,
            "rendered_html": None,
        }

    if not isinstance(html, str):
        return {
            "rendered_html": None,
            "cf_response": {"result_type": type(html).__name__},
            "error": "SDK returned non-string content.",
        }

    return {
        "rendered_html": html,
        "cf_response": None,
        "error": None,
    }
