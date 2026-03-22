"""Apply LangSmith / LangChain tracing settings to the process environment.

LangGraph reads ``LANGCHAIN_TRACING_V2`` and related variables at run time.
Call :func:`configure_langsmith` before invoking the graph (``build_graph`` does this).
"""

from __future__ import annotations

import os

from server.config import get_settings


def configure_langsmith() -> None:
    """Mirror :class:`~server.config.Settings` into ``os.environ`` for LangSmith."""
    s = get_settings()
    if s.langchain_tracing_v2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if s.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = s.langchain_api_key
        os.environ["LANGSMITH_API_KEY"] = s.langchain_api_key
    if s.langchain_project:
        os.environ["LANGCHAIN_PROJECT"] = s.langchain_project
        os.environ.setdefault("LANGSMITH_PROJECT", s.langchain_project)
    if s.langchain_endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = s.langchain_endpoint
        os.environ["LANGSMITH_ENDPOINT"] = s.langchain_endpoint
