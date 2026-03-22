from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    """State for the Browser Rendering LangGraph."""

    url: str
    extra_http_headers: dict[str, str]
    # wait_until, timeout (ms, max 60000). Avoid networkidle0 on chatty SPAs like Handshake.
    goto_options: dict[str, Any]
    # Default True in the node: proceed if waitUntil is flaky (Cloudflare API).
    best_attempt: bool
    # Post-navigation action budget (ms); default 120000 in the node.
    action_timeout_ms: float

    rendered_html: str | None
    cf_response: dict[str, Any] | None
    error: str | None
