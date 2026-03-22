from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    """State for the Browser Rendering LangGraph."""

    url: str
    extra_http_headers: dict[str, str]
    goto_options: dict[str, Any]

    rendered_html: str | None
    cf_response: dict[str, Any] | None
    error: str | None
