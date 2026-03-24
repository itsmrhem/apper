"""Fetch structured job details via Cloudflare Browser Rendering /json (Workers AI)."""

import asyncio
from html import escape
from typing import Any

from cloudflare import NOT_GIVEN, APIStatusError, AsyncCloudflare, CloudflareError

from server.cf_render_common import (
    extra_headers_for_sdk,
    goto_options_for_sdk,
    resolve_cookies,
)
from server.config import get_settings
from server.state import GraphState

_JOB_DETAIL_PROMPT = (
    "Extract structured fields from this Handshake job page. "
    "For `job_description`, copy the ENTIRE text of the job description"
    "Return non-empty `title`, `employer_name`, and `description` whenever visible."
)

_JOB_DETAIL_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "employer_name": {"type": "string"},
            "location": {"type": "string"},
            "employment_type": {"type": "string"},
            "application_url": {"type": "string"},
            "job_description": {"type": "string"},
            "looking-for": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["title", "employer_name", "description"],
    },
}

_EXPAND_MORE_SCRIPT = """
(() => {
  const isVisible = (el) => {
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s && s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
  };
  const textOf = (el) => ((el.innerText || el.textContent || '').trim().toLowerCase());
  const shouldClick = (el) => {
    const t = textOf(el);
    if (!t) return false;
    return (
      t === 'more' ||
      t.includes('show more') ||
      t.includes('see more') ||
      t.includes('read more') ||
      t.includes('view more')
    );
  };
  const clickCandidates = () => {
    const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], span, div'));
    for (const el of nodes) {
      if (!isVisible(el) || !shouldClick(el)) continue;
      try { el.click(); } catch (_) {}
    }
  };
  clickCandidates();
  setTimeout(clickCandidates, 400);
  setTimeout(clickCandidates, 900);
})();
"""


def _unwrap_json_result(payload: object) -> object:
    if isinstance(payload, dict) and "result" in payload:
        return payload.get("result")
    return payload


def _is_null_or_empty_extracted(extracted: object) -> bool:
    """True when /json succeeded (caller checks error) but structured payload is unusable."""
    if extracted is None:
        return True
    if not isinstance(extracted, dict):
        return False
    if not extracted:
        return True
    title = extracted.get("title")
    employer = extracted.get("employer_name")
    title_ok = isinstance(title, str) and bool(title.strip())
    emp_ok = isinstance(employer, str) and bool(employer.strip())
    return not (title_ok and emp_ok)


async def job_details_json_node(state: GraphState) -> dict[str, Any]:
    if state.get("error"):
        return {"job_details": [], "job_details_error": None}

    settings = get_settings()
    if not settings.cf_account_id or not settings.cf_api_token:
        return {"job_details": [], "job_details_error": "Set CF_ACCOUNT_ID and CF_API_TOKEN."}

    urls = state.get("job_urls_to_fetch") or []
    if not isinstance(urls, list):
        return {"job_details": [], "job_details_error": "State `job_urls_to_fetch` must be a list."}
    job_urls = [str(u).strip() for u in urls if str(u).strip()]
    if not job_urls:
        return {"job_details": [], "job_details_error": None}

    cookie_rows, cookie_err = resolve_cookies(state, settings)
    if cookie_err:
        return {"job_details": [], "job_details_error": cookie_err}

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

    use_md_fallback = state.get("job_detail_markdown_fallback")
    if use_md_fallback is None:
        use_md_fallback = True

    settle_ms = state.get("job_detail_settle_timeout_ms")
    if settle_ms is None:
        settle_ms = 8_000.0
    try:
        settle_ms = float(settle_ms)
    except (TypeError, ValueError):
        settle_ms = 8_000.0

    custom_ai_model = (state.get("job_detail_custom_ai_model") or settings.job_detail_custom_ai_model or "").strip()
    custom_ai_auth = (settings.job_detail_custom_ai_authorization or "").strip()
    custom_ai_extra_body: dict[str, Any] | None = None
    if custom_ai_model and custom_ai_auth:
        custom_ai_extra_body = {
            "custom_ai": [
                {
                    "model": custom_ai_model,
                    "authorization": custom_ai_auth,
                }
            ]
        }

    async def call_json_extract(
        client: AsyncCloudflare,
        *,
        url: str | None,
        page_html: str | None,
        goto_opts: Any,
        wait_for_timeout: Any,
    ) -> object:
        if page_html is not None:
            return await client.browser_rendering.json.create(
                account_id=settings.cf_account_id,
                html=page_html,
                cookies=cookies_arg,
                set_extra_http_headers=extra_headers,
                best_attempt=best,
                action_timeout=action_timeout,
                prompt=_JOB_DETAIL_PROMPT,
                response_format=_JOB_DETAIL_RESPONSE_FORMAT,
                timeout=180.0,
                extra_body=custom_ai_extra_body,
            )
        return await client.browser_rendering.json.create(
            account_id=settings.cf_account_id,
            url=url or "",
            add_script_tag=[{"content": _EXPAND_MORE_SCRIPT}],
            cookies=cookies_arg,
            set_extra_http_headers=extra_headers,
            goto_options=goto_opts,
            best_attempt=best,
            action_timeout=action_timeout,
            prompt=_JOB_DETAIL_PROMPT,
            response_format=_JOB_DETAIL_RESPONSE_FORMAT,
            wait_for_timeout=wait_for_timeout,
            timeout=180.0,
            extra_body=custom_ai_extra_body,
        )

    async def row_from_extract(
        client: AsyncCloudflare,
        url: str,
        *,
        goto_opts: Any,
        wait_for_timeout: Any,
        page_html: str | None = None,
        source: str,
    ) -> dict[str, Any]:
        try:
            raw = await call_json_extract(
                client,
                url=url if page_html is None else None,
                page_html=page_html,
                goto_opts=goto_opts,
                wait_for_timeout=wait_for_timeout,
            )
        except APIStatusError as exc:
            body = exc.body
            if body is not None and not isinstance(body, str):
                body = str(body)[:2000]
            elif isinstance(body, str):
                body = body[:2000]
            return {
                "url": url,
                "extracted": None,
                "error": f"HTTP {exc.status_code}: {exc.message}",
                "cf_body": body,
                "extract_source": source,
            }
        except CloudflareError as exc:
            return {
                "url": url,
                "extracted": None,
                "error": str(exc),
                "cf_body": None,
                "extract_source": source,
            }

        extracted = _unwrap_json_result(raw)
        return {
            "url": url,
            "extracted": extracted,
            "error": None,
            "cf_body": None,
            "extract_source": source,
        }

    async def one_primary(client: AsyncCloudflare, url: str) -> dict[str, Any]:
        return await row_from_extract(
            client,
            url,
            goto_opts=goto,
            wait_for_timeout=settle_ms if settle_ms > 0 else NOT_GIVEN,
            source="json+url+settle",
        )

    async def one_networkidle(client: AsyncCloudflare, url: str) -> dict[str, Any]:
        return await row_from_extract(
            client,
            url,
            goto_opts=goto_networkidle2,
            wait_for_timeout=5_000.0,
            source="json+url+networkidle2",
        )

    async def one_markdown_bridge(client: AsyncCloudflare, url: str) -> dict[str, Any]:
        try:
            md = await client.browser_rendering.markdown.create(
                account_id=settings.cf_account_id,
                url=url,
                add_script_tag=[{"content": _EXPAND_MORE_SCRIPT}],
                cookies=cookies_arg,
                set_extra_http_headers=extra_headers,
                goto_options=goto,
                best_attempt=best,
                action_timeout=action_timeout,
                wait_for_timeout=max(settle_ms, 10_000.0),
                timeout=180.0,
            )
        except APIStatusError as exc:
            body = exc.body
            if body is not None and not isinstance(body, str):
                body = str(body)[:2000]
            elif isinstance(body, str):
                body = body[:2000]
            return {
                "url": url,
                "extracted": None,
                "error": f"markdown HTTP {exc.status_code}: {exc.message}",
                "cf_body": body,
                "extract_source": "markdown_failed",
            }
        except CloudflareError as exc:
            return {
                "url": url,
                "extracted": None,
                "error": f"markdown: {exc}",
                "cf_body": None,
                "extract_source": "markdown_failed",
            }

        if not isinstance(md, str) or not md.strip():
            return {
                "url": url,
                "extracted": None,
                "error": "markdown returned empty",
                "cf_body": None,
                "extract_source": "markdown_empty",
            }

        wrapped = (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head>"
            f"<body><pre>{escape(md)}</pre></body></html>"
        )
        return await row_from_extract(
            client,
            url,
            goto_opts=NOT_GIVEN,
            wait_for_timeout=NOT_GIVEN,
            page_html=wrapped,
            source="json+markdown_html",
        )

    try:
        async with AsyncCloudflare(api_token=settings.cf_api_token) as client:
            rows: list[dict[str, Any]] = list(await asyncio.gather(*[one_primary(client, u) for u in job_urls]))

            retry_rounds = state.get("job_detail_null_retries")
            if retry_rounds is None:
                retry_rounds = 1
            try:
                retry_rounds = max(0, int(retry_rounds))
            except (TypeError, ValueError):
                retry_rounds = 1

            for round_i in range(retry_rounds):
                stale_idx = [
                    i
                    for i, r in enumerate(rows)
                    if r.get("error") is None and _is_null_or_empty_extracted(r.get("extracted"))
                ]
                if not stale_idx:
                    break
                retry_urls = [rows[i]["url"] for i in stale_idx]
                use_ni = round_i % 2 == 0
                retry_fn = one_networkidle if use_ni else one_primary
                retry_out = await asyncio.gather(*[retry_fn(client, u) for u in retry_urls])
                for i, rr in zip(stale_idx, retry_out, strict=True):
                    rows[i] = rr

            if use_md_fallback:
                stale_idx = [
                    i
                    for i, r in enumerate(rows)
                    if r.get("error") is None and _is_null_or_empty_extracted(r.get("extracted"))
                ]
                if stale_idx:
                    retry_urls = [rows[i]["url"] for i in stale_idx]
                    retry_out = await asyncio.gather(*[one_markdown_bridge(client, u) for u in retry_urls])
                    for i, rr in zip(stale_idx, retry_out, strict=True):
                        rows[i] = rr

    except CloudflareError as exc:
        return {"job_details": [], "job_details_error": str(exc)}

    return {"job_details": list(rows), "job_details_error": None}
