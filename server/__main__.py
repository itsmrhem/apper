"""CLI: run the LangGraph Browser Rendering graph once."""

import argparse
import asyncio
import json
import sys
from typing import Any

from server.graph import build_graph


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch rendered HTML via Cloudflare Browser Rendering (LangGraph).",
    )
    parser.add_argument("--url", required=True, help="URL to pass to the /content API")
    parser.add_argument(
        "--wait-until",
        default="load",
        help="goto_options.wait_until: load/domcontentloaded/networkidle2/networkidle0 "
        "(Handshake: use load; networkidle0 often times out)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=float,
        default=60_000.0,
        metavar="MS",
        help="goto_options.timeout in ms (max 60000; default 60000)",
    )
    parser.add_argument(
        "--no-goto-options",
        action="store_true",
        help="Omit gotoOptions (use API defaults: 30s nav timeout — often too short for SPAs)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full state as JSON (HTML may be large)",
    )
    args = parser.parse_args()

    initial: dict[str, Any] = {"url": args.url}
    if not args.no_goto_options:
        initial["goto_options"] = {
            "wait_until": args.wait_until,
            "timeout": min(args.timeout_ms, 60_000.0),
        }

    async def run():
        graph = build_graph()
        return await graph.ainvoke(initial)

    result = asyncio.run(run())

    if args.json:
        out = dict(result)
        html = out.get("rendered_html")
        if isinstance(html, str) and len(html) > 200_000:
            out["rendered_html"] = html[:200_000] + "\n... [truncated]"
        print(json.dumps(out, indent=2, default=str))
        return

    err = result.get("error")
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)
    html = result.get("rendered_html") or ""
    print(html)


if __name__ == "__main__":
    main()
