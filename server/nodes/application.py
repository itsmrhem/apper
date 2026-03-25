"""LaTeX resume/cover generation and PDF compile (per job)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from server.anthropic_messages import anthropic_text_completion, strip_latex_fence
from server.config import Settings, get_settings
from server.resume_sources import load_resume_blueprint_tex, load_resume_source_bundle
from server.state import GraphState


def _resume_system_from_blueprint(blueprint_tex: str) -> str:
    return (
        "You output ONE complete LaTeX file for pdfLaTeX.\n"
        "Output ONLY valid LaTeX (no markdown fences). Use pdfLaTeX-safe ASCII where possible.\n\n"
        "FORMAT (mandatory): Your file must follow the blueprint below exactly:\n"
        "- Same \\documentclass, \\usepackage lines, margin and length adjustments, "
        "\\newcommand / \\renewcommand definitions, \\titleformat, page style, and "
        "custom resume macros (e.g. \\resumeSubheading, \\resumeItem, \\resumeProjectHeading, list wrappers).\n"
        "- Same overall section structure and ordering as the blueprint (e.g. heading block, "
        "Skills Summary, Education, Experience, Projects, Achievements — keep that skeleton).\n"
        "- The blueprint may contain example body text: do NOT treat it as authoritative. "
        "Replace all substantive resume content using ONLY facts from the candidate source markdown; "
        "align emphasis and bullet ordering with the job posting JSON. "
        "Do not leave empty \\resumeItem{} placeholders.\n"
        "- Do not invent employers, degrees, dates, contact details, or awards. "
        "Header/contact lines must reflect the resume details in the sources.\n"
        "- Prefer one page; preserve the blueprint's spacing density.\n\n"
        "Blueprint (layout reference):\n---\n"
        + blueprint_tex.strip()
        + "\n---\n"
    )

_COVER_SYSTEM = """You write a complete LaTeX cover letter as a single file.
Output ONLY valid LaTeX (no markdown fences). pdfLaTeX-safe ASCII.
Requirements:
- \\documentclass[10pt]{article}
- \\usepackage[margin=0.75in]{geometry}
- At most ONE page; concise professional tone
- Reference the specific role and company from the job JSON
- Use only facts from sources; no fabricated credentials
"""


def _anthropic_key(settings: Settings) -> str:
    if settings.anthropic_api_key.strip():
        return settings.anthropic_api_key.strip()
    auth = (settings.job_detail_custom_ai_authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return auth


def _job_rows(state: GraphState) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in state.get("job_details") or []:
        if not isinstance(row, dict):
            continue
        ex = row.get("extracted")
        if not isinstance(ex, dict):
            continue
        if not str(ex.get("title") or "").strip():
            continue
        out.append(row)
    return out


def load_application_sources_node(state: GraphState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    settings = get_settings()
    text = load_resume_source_bundle(settings)
    blueprint, bp_err = load_resume_blueprint_tex(settings)
    if bp_err:
        return {
            "application_sources_text": text,
            "application_resume_blueprint_tex": "",
            "application_error": bp_err,
        }
    return {
        "application_sources_text": text,
        "application_resume_blueprint_tex": blueprint,
        "application_error": None,
    }


async def generate_resume_texes_node(state: GraphState) -> dict[str, Any]:
    if state.get("error") or state.get("application_error"):
        return {}
    settings = get_settings()
    key = _anthropic_key(settings)
    if not key:
        return {
            "application_error": "Set ANTHROPIC_API_KEY (or JOB_DETAIL_CUSTOM_AI_AUTHORIZATION=Bearer …) for resume generation.",
            "application_packages": [],
        }
    sources = state.get("application_sources_text") or load_resume_source_bundle(settings)
    blueprint = (state.get("application_resume_blueprint_tex") or "").strip()
    if not blueprint:
        return {
            "application_error": "Resume blueprint missing; check RESUME_BLUEPRINT_TEX_PATH and load_application_sources.",
            "application_packages": [],
        }
    rows = _job_rows(state)
    if not rows:
        return {"application_error": "No job details with titles to build resumes.", "application_packages": []}

    model = (settings.anthropic_resume_model or "claude-sonnet-4-20250514").strip()
    resume_system = _resume_system_from_blueprint(blueprint)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        ex = row.get("extracted") if isinstance(row.get("extracted"), dict) else {}
        user = (
            "Job posting (JSON):\n"
            + json.dumps(ex, indent=2, default=str)
            + "\n\nCandidate source markdown:\n"
            + sources
        )
        raw = await anthropic_text_completion(
            api_key=key,
            model=model,
            system=resume_system,
            user=user,
        )
        tex = strip_latex_fence(raw)
        return {
            "url": str(row.get("url") or ""),
            "extracted": ex,
            "resume_tex": tex,
            "resume_pdf_path": "",
            "cover_tex": "",
            "cover_pdf_path": "",
            "extract_source": row.get("extract_source"),
        }

    packages = await asyncio.gather(*[one(r) for r in rows])
    return {"application_packages": list(packages), "application_error": None}


async def generate_cover_texes_node(state: GraphState) -> dict[str, Any]:
    if state.get("error") or state.get("application_error"):
        return {}
    settings = get_settings()
    key = _anthropic_key(settings)
    model = (settings.anthropic_resume_model or "claude-sonnet-4-20250514").strip()
    sources = state.get("application_sources_text") or load_resume_source_bundle(settings)
    packages = list(state.get("application_packages") or [])
    if not packages:
        return {}

    async def one(pkg: dict[str, Any]) -> dict[str, Any]:
        ex = pkg.get("extracted") if isinstance(pkg.get("extracted"), dict) else {}
        user = (
            "Job posting (JSON):\n"
            + json.dumps(ex, indent=2, default=str)
            + "\n\nCandidate source markdown:\n"
            + sources
        )
        raw = await anthropic_text_completion(
            api_key=key,
            model=model,
            system=_COVER_SYSTEM,
            user=user,
        )
        pkg = dict(pkg)
        pkg["cover_tex"] = strip_latex_fence(raw)
        return pkg

    updated = await asyncio.gather(*[one(dict(p)) for p in packages])
    return {"application_packages": list(updated)}


def _run_pdflatex(tex: str, stem: str, pdflatex: str) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="apper-tex-"))
    tex_path = tmp / f"{stem}.tex"
    tex_path.write_text(tex, encoding="utf-8")
    cmd = [
        pdflatex,
        "-interaction=nonstopmode",
        f"-output-directory={tmp}",
        str(tex_path),
    ]
    for _ in range(2):
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            log = (proc.stdout or "") + "\n" + (proc.stderr or "")
            raise RuntimeError(f"pdflatex failed ({stem}): {log[-4000:]}")
    pdf = tmp / f"{stem}.pdf"
    if not pdf.is_file():
        raise RuntimeError(f"Missing PDF for {stem}")
    return str(pdf.resolve())


async def compile_resume_pdfs_node(state: GraphState) -> dict[str, Any]:
    if state.get("application_error"):
        return {}
    settings = get_settings()
    pdflatex = settings.pdflatex_path or "pdflatex"
    packages = list(state.get("application_packages") or [])

    async def compile_one(i: int, pkg: dict[str, Any]) -> dict[str, Any]:
        pkg = dict(pkg)
        stem = f"resume_{i}"
        try:
            pkg["resume_pdf_path"] = await asyncio.to_thread(
                _run_pdflatex, pkg.get("resume_tex") or "", stem, pdflatex
            )
        except Exception as exc:
            pkg["resume_pdf_error"] = str(exc)
        return pkg

    updated = await asyncio.gather(*[compile_one(i, dict(p)) for i, p in enumerate(packages)])
    errs = [p.get("resume_pdf_error") for p in updated if p.get("resume_pdf_error")]
    if errs:
        return {"application_packages": list(updated), "application_error": errs[0]}
    return {"application_packages": list(updated), "application_error": None}


async def compile_cover_pdfs_node(state: GraphState) -> dict[str, Any]:
    if state.get("application_error"):
        return {}
    settings = get_settings()
    pdflatex = settings.pdflatex_path or "pdflatex"
    packages = list(state.get("application_packages") or [])

    async def compile_one(i: int, pkg: dict[str, Any]) -> dict[str, Any]:
        pkg = dict(pkg)
        stem = f"cover_{i}"
        try:
            pkg["cover_pdf_path"] = await asyncio.to_thread(
                _run_pdflatex, pkg.get("cover_tex") or "", stem, pdflatex
            )
        except Exception as exc:
            pkg["cover_pdf_error"] = str(exc)
        return pkg

    updated = await asyncio.gather(*[compile_one(i, dict(p)) for i, p in enumerate(packages)])
    errs = [p.get("cover_pdf_error") for p in updated if p.get("cover_pdf_error")]
    if errs:
        return {"application_packages": list(updated), "application_error": errs[0]}
    return {"application_packages": list(updated), "application_error": None}
