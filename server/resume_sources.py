"""Load Markdown resume source files from Settings paths."""

from pathlib import Path

from server.config import Settings


def load_resume_source_bundle(settings: Settings) -> str:
    """Concatenate labeled sections for LLM context."""
    parts: list[str] = []

    def add(label: str, path_str: str) -> None:
        p = (path_str or "").strip()
        if not p:
            return
        path = Path(p).expanduser()
        if not path.is_file():
            parts.append(f"## {label}\n\n_(file not found: {path})_\n\n")
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            parts.append(f"## {label}\n\n_(read error: {exc})_\n\n")
            return
        parts.append(f"## {label}\n\n{text.strip()}\n\n")

    add("Resume details (contact, education, achievements)", settings.resume_details_path)
    add("Additional (professional) experience", settings.additional_experience_path)
    add("Educational experience", settings.educational_experience_path)
    add("Projects", settings.projects_path)

    return "".join(parts).strip() or "(no resume source files configured)"


def load_resume_blueprint_tex(settings: Settings) -> tuple[str, str | None]:
    """Return (tex_content, error_message). Empty content with error if misconfigured."""
    p = (settings.resume_blueprint_tex_path or "").strip()
    if not p:
        return "", "Set RESUME_BLUEPRINT_TEX_PATH to your resume blueprint .tex file."
    path = Path(p).expanduser()
    if not path.is_file():
        return "", f"Resume blueprint not found: {path}"
    try:
        return path.read_text(encoding="utf-8").strip(), None
    except OSError as exc:
        return "", f"Could not read resume blueprint {path}: {exc}"
