"""Parse Handshake job links from listing markdown."""

from typing import Any

from server.handshake_job_urls import extract_ordered_job_urls, select_job_urls_to_fetch
from server.state import GraphState


def parse_job_links_node(state: GraphState) -> dict[str, Any]:
    if state.get("error"):
        return {
            "job_links_found": [],
            "job_urls_to_fetch": [],
            "parse_job_links_error": None,
        }

    md = state.get("rendered_html") or ""
    if not isinstance(md, str) or not md.strip():
        return {
            "job_links_found": [],
            "job_urls_to_fetch": [],
            "parse_job_links_error": "No listing markdown in state (`rendered_html`).",
        }

    found = extract_ordered_job_urls(md)
    seen = state.get("seen_job_urls")
    if seen is not None and not isinstance(seen, list):
        return {
            "job_links_found": found,
            "job_urls_to_fetch": [],
            "parse_job_links_error": "State `seen_job_urls` must be a list of strings when set.",
        }
    seen_set = frozenset(str(u) for u in seen) if seen else frozenset()

    skip = state.get("skip_first_listing_job_url")
    if skip is None:
        skip = False
    max_d = state.get("max_job_details")
    if max_d is None:
        max_d = 5
    try:
        max_i = int(max_d)
    except (TypeError, ValueError):
        max_i = 5

    to_fetch = select_job_urls_to_fetch(
        found,
        seen_job_urls=seen_set,
        skip_first=bool(skip),
        max_details=max_i,
    )

    err: str | None = None
    if not found:
        err = "No Handshake /job-search/<id> or /jobs/… URLs found in listing markdown."
    elif not to_fetch:
        err = "Job URLs were found but none selected (check skip_first / seen_job_urls / max_job_details)."

    return {
        "job_links_found": found,
        "job_urls_to_fetch": to_fetch,
        "parse_job_links_error": err,
    }
