"""Single LangGraph node: Cloudflare Browser Rendering via the official Python SDK."""

from typing import Any

from cloudflare import NOT_GIVEN, APIStatusError, AsyncCloudflare, CloudflareError

from server.config import Settings, get_settings
from server.state import GraphState


def _goto_options_for_sdk(raw: dict[str, Any] | None) -> Any:
    if not raw:
        return NOT_GIVEN
    out: dict[str, Any] = {}
    if "wait_until" in raw:
        out["wait_until"] = raw["wait_until"]
    elif "waitUntil" in raw:
        out["wait_until"] = raw["waitUntil"]
    if "timeout" in raw:
        out["timeout"] = raw["timeout"]
    if "referer" in raw:
        out["referer"] = raw["referer"]
    elif "referrer" in raw:
        out["referer"] = raw["referrer"]
    return out if out else NOT_GIVEN


def _extra_headers(state: GraphState, settings: Settings) -> Any:
    headers = dict(state.get("extra_http_headers") or {})
    if settings.handshake_cookie and "Cookie" not in headers and "cookie" not in headers:
        headers["Cookie"] = settings.handshake_cookie
    return headers if headers else NOT_GIVEN


async def browser_render_node(state: GraphState) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cf_account_id or not settings.cf_api_token:
        return {"error": "Set CF_ACCOUNT_ID and CF_API_TOKEN in the environment."}

    url = (state.get("url") or "").strip()
    if not url:
        return {"error": "State must include a non-empty `url`."}

    goto = _goto_options_for_sdk(state.get("goto_options"))
    extra_headers = _extra_headers(state, settings)

    try:
        async with AsyncCloudflare(api_token=settings.cf_api_token) as client:
            html = await client.browser_rendering.content.create(
                account_id=settings.cf_account_id,
                url=url,
                set_extra_http_headers=extra_headers,
                goto_options=goto,
                timeout=120.0,
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
