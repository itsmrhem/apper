from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    """State for the Browser Rendering LangGraph."""

    url: str
    # Puppeteer-style cookies; overrides file/env when set.
    cookies: list[dict[str, Any]]
    # JSON cookie file path (optional; when unset, Settings.handshake_cookies_path is used).
    cookies_path: str

    extra_http_headers: dict[str, str]
    # wait_until, timeout (ms, max 60000). Avoid networkidle0 on chatty SPAs like Handshake.
    goto_options: dict[str, Any]
    # Default True in the node: proceed if waitUntil is flaky (Cloudflare API).
    best_attempt: bool
    # Post-navigation action budget (ms); default 120000 in the node.
    action_timeout_ms: float
    # After navigation, wait this many ms before markdown snapshot (Handshake SPA); default 8000 in node.
    listing_markdown_wait_ms: float

    rendered_html: str | None
    cf_response: dict[str, Any] | None
    error: str | None

    # Listing → detail pipeline (optional graph)
    max_job_details: int
    skip_first_listing_job_url: bool
    seen_job_urls: list[str]
    job_links_found: list[str]
    job_urls_to_fetch: list[str]
    parse_job_links_error: str | None
    job_details: list[dict[str, Any]]
    job_details_error: str | None
    # Extra /json attempts per URL when extraction is null/empty (default 1 in node).
    job_detail_null_retries: int
    # After navigation, wait this many ms before AI extraction (SPA paint); default 8000 in node.
    job_detail_settle_timeout_ms: float
    # If /json still empty, render markdown then extract from that text (extra API calls).
    job_detail_markdown_fallback: bool
    # Optional Cloudflare /json custom AI override.
    job_detail_custom_ai_model: str
