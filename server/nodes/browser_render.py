"""Single LangGraph node: Cloudflare Browser Rendering via the official Python SDK."""

from typing import Any

from cloudflare import NOT_GIVEN, APIStatusError, AsyncCloudflare, CloudflareError

from server.cf_render_common import (
    extra_headers_for_sdk,
    goto_options_for_sdk,
    resolve_cookies,
)
from server.config import get_settings
from server.state import GraphState


def _is_empty_markdown(content: object) -> bool:
    return not isinstance(content, str) or not content.strip()


async def browser_render_node(state: GraphState) -> dict[str, Any]:
    settings = get_settings()
    if not settings.cf_account_id or not settings.cf_api_token:
        return {"error": "Set CF_ACCOUNT_ID and CF_API_TOKEN in the environment."}

    url = (state.get("url") or "").strip()
    if not url:
        return {"error": "State must include a non-empty `url`."}

    cookie_rows, cookie_err = resolve_cookies(state, settings)
    if cookie_err:
        return {"error": cookie_err, "rendered_html": None, "cf_response": None}

    goto = goto_options_for_sdk(state.get("goto_options"))
    raw_goto = dict(state.get("goto_options") or {})
    raw_goto["wait_until"] = "networkidle2"
    raw_goto["timeout"] = min(float(raw_goto.get("timeout", 60_000)), 60_000.0)
    goto_networkidle2 = goto_options_for_sdk(raw_goto)

    extra_headers = extra_headers_for_sdk(
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
        action_timeout = 120_000.0

    settle = state.get("listing_markdown_wait_ms")
    if settle is None:
        settle = 8_000.0
    try:
        settle = float(settle)
    except (TypeError, ValueError):
        settle = 8_000.0

    wait_primary = settle if settle > 0 else NOT_GIVEN
    wait_long = max(settle, 12_000.0) if settle > 0 else 12_000.0

    async def fetch_markdown(
        client: AsyncCloudflare,
        *,
        goto_opts: Any,
        wait_for_timeout: Any,
    ) -> str | object:
        return await client.browser_rendering.markdown.create(
            account_id=settings.cf_account_id,
            url=url,
            cookies=cookies_arg,
            set_extra_http_headers=extra_headers,
            goto_options=goto_opts,
            best_attempt=best,
            action_timeout=action_timeout,
            wait_for_timeout=wait_for_timeout,
            timeout=180.0,
        )

    try:
        async with AsyncCloudflare(api_token=settings.cf_api_token) as client:
            html = await fetch_markdown(client, goto_opts=goto, wait_for_timeout=wait_primary)

            if _is_empty_markdown(html):
                html = await fetch_markdown(
                    client,
                    goto_opts=goto_networkidle2,
                    wait_for_timeout=5_000.0,
                )

            if _is_empty_markdown(html):
                html = await fetch_markdown(
                    client,
                    goto_opts=goto,
                    wait_for_timeout=wait_long,
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

    if _is_empty_markdown(html):
        return {
            "rendered_html": None,
            "cf_response": None,
            "error": (
                "Browser Rendering returned empty markdown after load+settle, networkidle2, and a long settle. "
                "Handshake often needs valid session cookies (HANDSHAKE_COOKIES_PATH), or try "
                "--listing-settle-ms 15000 and --wait-until domcontentloaded."
            ),
        }

    return {
        "rendered_html": html,
        "cf_response": None,
        "error": None,
    }
