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
- **`--wait-until networkidle0`** (default) maps to `gotoOptions.waitUntil` for SPAs.
- **`--no-goto-options`** uses API defaults.
- **`--json`** prints the final state as JSON (truncates very large HTML).

Console script: **`apper-render`** (same flags).

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
            "goto_options": {"wait_until": "networkidle0"},
        }
    )

asyncio.run(main())
```

## Layout

- [`server/graph.py`](server/graph.py) — `StateGraph`: `START → browser_render → END`
- [`server/nodes/browser_render.py`](server/nodes/browser_render.py) — Cloudflare `/content` `POST`
- [`server/state.py`](server/state.py) — `GraphState`
- [`server/config.py`](server/config.py) — env-based settings

## Risks

- Session cookies expire; rotate `HANDSHAKE_COOKIE` as needed.
- Respect Cloudflare quotas and Handshake terms of use.
