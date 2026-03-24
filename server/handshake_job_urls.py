"""Extract Handshake job detail URLs from listing markdown."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

# Stu job posts: .../stu/jobs/<id>
_JOB_STU_RE = re.compile(
    r"https?://(?:[a-zA-Z0-9-]+\.)?joinhandshake\.com(?:/stu)?/jobs/[a-zA-Z0-9-]+",
    re.IGNORECASE,
)
# Listing / overlay URLs: .../job-search/<numeric_id>?...
_JOB_SEARCH_RE = re.compile(
    r"https?://(?:[a-zA-Z0-9-]+\.)?joinhandshake\.com/job-search/[0-9]+(?:\?[^)\s\]]*)?",
    re.IGNORECASE,
)
# Broken markdown often concatenates:
# .../job-search?query=...&page=1/job-search/10871841?query=...
# We locate the first .../job-search/<digits>? on the host and rebuild.
_ORIGIN_RE = re.compile(
    r"(https?://(?:[a-zA-Z0-9-]+\.)?joinhandshake\.com)",
    re.IGNORECASE,
)
_JOB_SEARCH_ID_RE = re.compile(
    r"/job-search/([0-9]+)(\?[^)\s\]]*)?",
    re.IGNORECASE,
)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")


def _dedupe_key(url: str) -> str:
    p = urlparse(url)
    path = p.path.rstrip("/") or p.path
    return f"{p.netloc.lower()}{path}"


def _from_job_search_path(raw: str) -> str | None:
    """Build https://host/job-search/<id>?... from any string that contains that segment."""
    raw = raw.strip().rstrip(").,;\"'")
    om = _ORIGIN_RE.match(raw)
    if not om:
        return None
    origin = om.group(1).rstrip("/")
    jm = _JOB_SEARCH_ID_RE.search(raw)
    if not jm:
        return None
    job_id = jm.group(1)
    query = jm.group(2) or ""
    return f"{origin}/job-search/{job_id}{query}"


def _from_stu_jobs_path(raw: str) -> str | None:
    raw = raw.strip().rstrip(").,;\"'")
    m = _JOB_STU_RE.search(raw)
    if not m:
        return None
    hit = m.group(0)
    parsed = urlparse(hit.split("?")[0] if "?" in hit else hit)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/") or parsed.path
    q = urlparse(hit).query
    if q:
        return urlunparse((parsed.scheme, parsed.netloc, path, "", q, ""))
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _normalize_job_url(raw: str) -> str | None:
    u = raw.strip().rstrip(").,;\"'")
    # Prefer /job-search/<id> (listing overlay) — also repairs concatenated markdown URLs.
    js = _from_job_search_path(u)
    if js:
        return js
    # Clean job-search URL without needing repair
    m = _JOB_SEARCH_RE.search(u)
    if m:
        return _from_job_search_path(m.group(0)) or m.group(0)
    # Classic stu/jobs links
    stu = _from_stu_jobs_path(u)
    if stu:
        return stu
    m2 = _JOB_STU_RE.search(u)
    if m2:
        return _from_stu_jobs_path(m2.group(0))
    return None


def extract_ordered_job_urls(markdown: str) -> list[str]:
    """Unique job URLs in first-seen order (markdown links first, then bare URLs)."""
    seen: set[str] = set()
    ordered: list[str] = []

    def push(norm: str | None) -> None:
        if not norm:
            return
        key = _dedupe_key(norm)
        if key in seen:
            return
        seen.add(key)
        ordered.append(norm)

    for m in _MD_LINK_RE.finditer(markdown):
        push(_normalize_job_url(m.group(1)))

    for m in _JOB_SEARCH_RE.finditer(markdown):
        push(_normalize_job_url(m.group(0)))

    for m in _JOB_STU_RE.finditer(markdown):
        push(_normalize_job_url(m.group(0)))

    # Mangled listing links (…/job-search?…/job-search/<id>?…) often fail _JOB_SEARCH_RE.
    bare = re.finditer(
        r"https?://[^\s)\]>\"']+",
        markdown,
        re.IGNORECASE,
    )
    for m in bare:
        chunk = m.group(0).rstrip(").,;\"'")
        if "joinhandshake.com" in chunk.lower() and "/job-search/" in chunk.lower():
            push(_normalize_job_url(chunk))

    return ordered


def select_job_urls_to_fetch(
    ordered_urls: list[str],
    *,
    seen_job_urls: frozenset[str] | set[str] | None,
    skip_first: bool,
    max_details: int,
) -> list[str]:
    urls = list(ordered_urls)
    if skip_first and urls:
        urls = urls[1:]
    if seen_job_urls:
        urls = [u for u in urls if u not in seen_job_urls]
    return urls[: max(0, max_details)]
