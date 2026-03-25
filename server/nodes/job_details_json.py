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
    "Extract structured fields from this Handshake job posting page. "
    "Reply with ONLY one JSON object. Do not use markdown, do not wrap in ```, do not add any text before or after the JSON. "
    "Every value must be a JSON string; use \"\" if a field is missing or unknown. "
    "Include these keys exactly: title, employer_name, location, employment_type, job_description, looking_for, summary. "
    "For job_description, use the full visible job description text. "
    "If the description is extremely long, truncate job_description to at most 12000 characters and end with \" …[truncated]\" "
    "so the overall reply stays valid JSON."
)

# When the API returns 422 (model text did not parse as schema JSON), retry with stricter size cap — common cause is truncated JSON.
_JOB_DETAIL_PROMPT_RETRY = (
    "Extract Handshake job fields. Output ONLY one JSON object, valid JSON, no markdown or code fences, no commentary. "
    "All values must be strings; use \"\" if unknown. Keys: title, employer_name, location, employment_type, "
    "job_description, looking_for, summary. "
    "Keep job_description under 6000 characters (truncate with \" …[truncated]\" if needed); prioritize the start of the description."
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
            "job_description": {"type": "string"},
            "looking_for": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": [
            "title",
            "employer_name",
            "location",
            "employment_type",
            "job_description",
            "looking_for",
            "summary",
        ],
        "additionalProperties": False,
    },
}

_EXPAND_MORE_SCRIPT = """
(() => {
  const isVisible = (el) => {
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s && s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
  };
  const inMainContent = (el) => {
    let p = el;
    for (let i = 0; i < 12 && p; i++, p = p.parentElement) {
      const r = (p.getAttribute && p.getAttribute('role')) || '';
      if (r === 'navigation' || r === 'banner') return false;
      const id = ((p.id || '') + ' ' + (p.className || '')).toLowerCase();
      if (id.includes('nav') && id.includes('header')) return false;
    }
    return true;
  };
  const norm = (t) => (String(t || '').replace(/\\s+/g, ' ').trim().toLowerCase());
  const hasHandshakeViewMore = (el) => {
    const cn = String((el.className != null && el.className) || '');
    return cn.includes('view-more-button');
  };
  const shouldClickText = (t) => {
    if (!t) return false;
    if (t.length > 120) return false;
    if (/\\b(show|read|see|view)\\s+more\\b/.test(t)) return true;
    if (/\\b(show|see)\\s+full(\\s+description)?\\b/.test(t)) return true;
    if (/\\bexpand\\b/.test(t) && t.length <= 40) return true;
    if (t === 'more' || t === '…' || t === '...' || t === '… more' || t === '... more') return true;
    if (/^…\\s*more$/.test(t) || /^\\.\\.\\.\\s*more$/.test(t)) return true;
    if (t.length <= 22 && /\\bmore\\b/.test(t)) return true;
    return false;
  };
  const shouldClickAria = (rawAria) => {
    const a = String(rawAria || '').trim().toLowerCase();
    if (!a) return false;
    if (/^show\\s+more\\b/.test(a)) return true;
    if (/\\b(read|see|view)\\s+more\\b/.test(a)) return true;
    if (/\\bexpand\\b/.test(a) && a.length < 200) return true;
    return false;
  };
  const shouldClickEl = (el) => {
    // Handshake official control: do not use inMainContent — some layouts nest oddly and we would skip.
    if (hasHandshakeViewMore(el)) return isVisible(el);
    if (!inMainContent(el)) return false;
    const t = norm(el.innerText || el.textContent || '');
    if (shouldClickText(t)) return true;
    if (shouldClickAria(el.getAttribute('aria-label'))) return true;
    return false;
  };
  const scrollNudge = () => {
    try {
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      window.scrollTo({ top: document.documentElement.scrollHeight, left: 0, behavior: 'instant' });
      const roots = document.querySelectorAll('main, [role="main"], article, [data-testid*="job"]');
      roots.forEach((root) => {
        try {
          root.scrollTop = root.scrollHeight;
        } catch (_) {}
      });
    } catch (_) {}
  };
  const fireClick = (el) => {
    try {
      el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
      if (typeof el.focus === 'function') {
        try { el.focus({ preventScroll: true }); } catch (_) {}
      }
      el.click();
      el.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    } catch (_) {}
  };
  const clickCandidates = () => {
    scrollNudge();
    const byClass = Array.from(
      document.querySelectorAll('button[class*="view-more-button"], [class*="view-more-button"]')
    );
    const sel = [
      'button', 'a', '[role="button"]', '[role="link"]',
      'span[tabindex]', 'div[tabindex]', 'div[role="button"]',
    ].join(', ');
    const seen = new Set();
    const nodes = [];
    for (const el of [...byClass, ...Array.from(document.querySelectorAll(sel))]) {
      if (seen.has(el)) continue;
      seen.add(el);
      nodes.push(el);
    }
    for (const el of nodes) {
      if (!isVisible(el) || !shouldClickEl(el)) continue;
      fireClick(el);
    }
  };
  const run = () => {
    clickCandidates();
  };
  run();
  [200, 450, 800, 1300, 2000, 3200, 5000, 7500, 10500, 14000, 17500, 21000].forEach((ms) => setTimeout(run, ms));
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
        # Expand script last pass ~21s; wait after so JD text is in DOM before /json.
        settle_ms = 24_000.0
    try:
        settle_ms = float(settle_ms)
    except (TypeError, ValueError):
        settle_ms = 24_000.0

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
        prompt: str,
    ) -> object:
        if page_html is not None:
            return await client.browser_rendering.json.create(
                account_id=settings.cf_account_id,
                html=page_html,
                cookies=cookies_arg,
                set_extra_http_headers=extra_headers,
                best_attempt=best,
                action_timeout=action_timeout,
                prompt=prompt,
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
            prompt=prompt,
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
        prompts = [_JOB_DETAIL_PROMPT, _JOB_DETAIL_PROMPT_RETRY]
        raw: object | None = None
        for attempt, prompt in enumerate(prompts):
            try:
                raw = await call_json_extract(
                    client,
                    url=url if page_html is None else None,
                    page_html=page_html,
                    goto_opts=goto_opts,
                    wait_for_timeout=wait_for_timeout,
                    prompt=prompt,
                )
                break
            except APIStatusError as exc:
                if exc.status_code == 422 and attempt + 1 < len(prompts):
                    continue
                body = exc.body
                if body is not None and not isinstance(body, str):
                    body = str(body)[:4000]
                elif isinstance(body, str):
                    body = body[:4000]
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
