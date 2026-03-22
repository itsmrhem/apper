# Apper — LangGraph + Cloudflare Browser Rendering

Single **[LangGraph](https://langchain-ai.github.io/langgraph/)** graph with **one node** that uses the official **[Cloudflare Python library](https://developers.cloudflare.com/api/python/)** (`AsyncCloudflare`) to call **Browser Rendering** [`content.create`](https://developers.cloudflare.com/api/python/resources/browser_rendering/subresources/content/methods/create/). Use it to fetch fully rendered HTML for JavaScript-heavy pages (e.g. Handshake) using your session cookie when needed.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set CF_ACCOUNT_ID, CF_API_TOKEN
```

## Run (CLI)

```bash
python -m server --url "https://example.com"
```

- **`HANDSHAKE_COOKIE`** in `.env` is sent as `Cookie` unless you override with graph state `extra_http_headers`.
- **`--wait-until load`** (default) — Handshake and similar SPAs often **never** reach `networkidle0`, which triggers a 30s navigation timeout; use `load` or `domcontentloaded`, or `networkidle2` if you need stricter idleness.
- **`--timeout-ms 60000`** (default, max allowed) — raises Cloudflare’s navigation timeout from the API default (30s).
- **`--no-goto-options`** uses API defaults (short timeout — often fails on heavy SPAs).
- **`--json`** prints the final state as JSON (truncates very large HTML).

Console script: **`apper-render`** (same flags).

## LangSmith tracing

Tracing is off by default. To send LangGraph runs to [LangSmith](https://docs.smith.langchain.com/):

1. Set in `.env` (see [`.env.example`](.env.example)):
   - `LANGCHAIN_TRACING_V2=true`
   - `LANGCHAIN_API_KEY=` (or `LANGSMITH_API_KEY`)
   - `LANGCHAIN_PROJECT=apper` (or `LANGSMITH_PROJECT`)
2. Optional: `LANGCHAIN_ENDPOINT` / `LANGSMITH_ENDPOINT` (e.g. EU host).

[`build_graph()`](server/graph.py) calls [`configure_langsmith()`](server/tracing.py), which copies these settings into `os.environ` so LangChain/LangGraph pick them up. You can also call `configure_langsmith()` yourself before invoking the graph if you load settings another way.

## Programmatic use

```python
import asyncio
from server.graph import build_graph

async def main():
    graph = build_graph()
    return await graph.ainvoke(
        {
            "url": "https://…",
            "extra_http_headers": {"Cookie": "…"},
            "goto_options": {"wait_until": "load", "timeout": 60000},
        }
    )

asyncio.run(main())
```

## Layout

- [`server/graph.py`](server/graph.py) — `StateGraph`: `START → browser_render → END`
- [`server/nodes/browser_render.py`](server/nodes/browser_render.py) — Cloudflare `/content` `POST`
- [`server/state.py`](server/state.py) — `GraphState`
- [`server/config.py`](server/config.py) — env-based settings (incl. LangSmith)
- [`server/tracing.py`](server/tracing.py) — `configure_langsmith()` → `os.environ`

## Risks

- Session cookies expire; rotate `HANDSHAKE_COOKIE` as needed.
- Respect Cloudflare quotas and Handshake terms of use.
