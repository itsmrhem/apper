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
        "--listing-settle-ms",
        type=float,
        default=8_000.0,
        metavar="MS",
        help="After navigation, wait MS before markdown capture (Handshake listing SPA); default 8000. Use 0 to skip.",
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
    parser.add_argument(
        "--job-details",
        action="store_true",
        help="After listing markdown, parse /jobs/… links and fetch structured details via /json (Workers AI).",
    )
    parser.add_argument(
        "--max-job-details",
        type=int,
        default=5,
        metavar="N",
        help="Max job detail pages to fetch after filtering (default 5).",
    )
    parser.add_argument(
        "--skip-first-listing-job",
        action="store_true",
        help="Do not fetch the first job URL in listing order (use if that job is already fully shown on the list page).",
    )
    parser.add_argument(
        "--seen-job-urls-file",
        metavar="PATH",
        default="",
        help='JSON array of job URLs to skip, e.g. ["https://school.joinhandshake.com/stu/jobs/abc"]',
    )
    parser.add_argument(
        "--job-detail-null-retries",
        type=int,
        default=1,
        metavar="N",
        help="When /json returns null/empty fields, retry that URL up to N extra times (default 1). Use 0 to disable.",
    )
    parser.add_argument(
        "--job-detail-settle-ms",
        type=float,
        default=24_000.0,
        metavar="MS",
        help="After page load + expand-more script, wait MS before /json extraction; default 24000 (Handshake JD).",
    )
    parser.add_argument(
        "--no-job-detail-markdown-fallback",
        action="store_true",
        help="Disable markdown render + /json(html) fallback when URL-based /json returns empty.",
    )
    parser.add_argument(
        "--application",
        action="store_true",
        help="After job details: tailor LaTeX resume + cover per job and compile PDFs (implies --job-details).",
    )
    args = parser.parse_args()

    with_job_details = bool(args.job_details or args.application)

    initial: dict[str, Any] = {
        "url": args.url,
        "listing_markdown_wait_ms": max(0.0, args.listing_settle_ms),
    }
    if not args.no_goto_options:
        initial["goto_options"] = {
            "wait_until": args.wait_until,
            "timeout": min(args.timeout_ms, 60_000.0),
        }

    if with_job_details:
        initial["max_job_details"] = max(0, args.max_job_details)
        initial["skip_first_listing_job_url"] = args.skip_first_listing_job
        initial["job_detail_null_retries"] = max(0, args.job_detail_null_retries)
        initial["job_detail_settle_timeout_ms"] = max(0.0, args.job_detail_settle_ms)
        initial["job_detail_markdown_fallback"] = not args.no_job_detail_markdown_fallback
        if args.seen_job_urls_file.strip():
            path = args.seen_job_urls_file.strip()
            try:
                with open(path, encoding="utf-8") as f:
                    seen = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Invalid --seen-job-urls-file {path}: {exc}", file=sys.stderr)
                sys.exit(1)
            if not isinstance(seen, list):
                print("--seen-job-urls-file must contain a JSON array.", file=sys.stderr)
                sys.exit(1)
            initial["seen_job_urls"] = [str(u) for u in seen]

    async def run():
        if args.application:
            graph = build_graph(with_job_details=True, with_application=True)
            return await graph.ainvoke(initial)
        graph = build_graph(with_job_details=with_job_details)
        return await graph.ainvoke(initial)

    result = asyncio.run(run())

    if args.json:
        out = dict(result)
        html = out.get("rendered_html")
        if isinstance(html, str) and len(html) > 200_000:
            out["rendered_html"] = html[:200_000] + "\n... [truncated]"
        pkgs = out.get("application_packages")
        if isinstance(pkgs, list):
            for p in pkgs:
                if not isinstance(p, dict):
                    continue
                for k in ("resume_tex", "cover_tex"):
                    s = p.get(k)
                    if isinstance(s, str) and len(s) > 8_000:
                        p[k] = s[:8_000] + "\n... [truncated]"
        print(json.dumps(out, indent=2, default=str))
        if args.application and out.get("application_error"):
            sys.exit(1)
        return

    err = result.get("error")
    if err:
        print(err, file=sys.stderr)
        sys.exit(1)
    html = result.get("rendered_html") or ""
    print(html)
    if with_job_details and not args.json:
        details = result.get("job_details")
        if details is not None:
            print("\n--- job details (structured) ---\n")
            print(json.dumps(details, indent=2, default=str))
        perr = result.get("parse_job_links_error")
        jerr = result.get("job_details_error")
        if perr:
            print(f"\n[parse_job_links] {perr}", file=sys.stderr)
        if jerr:
            print(f"\n[job_details_json] {jerr}", file=sys.stderr)
        tgerr = result.get("telegram_job_listing_error")
        tgsent = result.get("telegram_job_listing_sent_count")
        if tgerr:
            print(f"\n[telegram_job_listing] {tgerr}", file=sys.stderr)
        elif isinstance(tgsent, int):
            print(f"\n[telegram_job_listing] sent {tgsent} message(s).", file=sys.stderr)
        if args.application:
            aerr = result.get("application_error")
            if aerr:
                print(f"\n[application] {aerr}", file=sys.stderr)
            pkgs = result.get("application_packages")
            if isinstance(pkgs, list) and pkgs:
                print("\n--- application PDFs (paths on disk) ---\n")
                for i, p in enumerate(pkgs):
                    if not isinstance(p, dict):
                        continue
                    print(f"[{i}] resume: {p.get('resume_pdf_path', '')}")
                    print(f"[{i}] cover:  {p.get('cover_pdf_path', '')}")
            if aerr:
                sys.exit(1)


if __name__ == "__main__":
    main()
