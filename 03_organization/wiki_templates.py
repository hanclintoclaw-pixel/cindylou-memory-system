#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
WIKI_ROOT = P.code_root / "campaign-wiki"
TEMPLATES_ROOT = WIKI_ROOT / "Templates"
CONFORMANCE_REPORT = TEMPLATES_ROOT / "TEMPLATE_CONFORMANCE.md"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

TYPE_TO_TEMPLATE = {
    "arc": "Arc.md",
    "clue": "Clue.md",
    "entity": "NPC.md",
    "faction": "Faction.md",
    "faction-secret": "True-Names.md",
    "location": "Location.md",
    "npc": "NPC.md",
    "organization": "Organization.md",
    "pc": "PC.md",
    "recap": "Recap.md",
    "session": "Session.md",
    "tech": "Tech.md",
    "true-names": "True-Names.md",
    "vehicle": "Vehicle.md",
}

PATH_TO_TEMPLATE = {
    "Arcs": "Arc.md",
    "Clues": "Clue.md",
    "Factions": "Faction.md",
    "Locations": "Location.md",
    "NPCs": "NPC.md",
    "Organizations": "Organization.md",
    "PCs": "PC.md",
    "Recaps": "Recap.md",
    "Sessions": "Session.md",
    "Tech": "Tech.md",
    "Vehicles": "Vehicle.md",
}


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    path: Path
    headings: tuple[str, ...]
    fields: tuple[str, ...]


@dataclass(frozen=True)
class ConformanceResult:
    page: Path
    template_name: str
    missing_headings: tuple[str, ...]
    missing_fields: tuple[str, ...]
    ok: bool


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.startswith(" ") or line.startswith("-"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        data[key.strip()] = val.strip().strip('"')
    return data, text[match.end():]


def markdown_headings(text: str, level: int = 2) -> tuple[str, ...]:
    out: list[str] = []
    for marker, heading in HEADING_RE.findall(text):
        if len(marker) == level:
            out.append(heading.strip())
    return tuple(out)


def template_fields(template_text: str) -> tuple[str, ...]:
    frontmatter, _ = split_frontmatter(template_text)
    return tuple(frontmatter.keys())


def load_template(template_name: str) -> TemplateSpec:
    path = TEMPLATES_ROOT / template_name
    if not path.exists():
        raise FileNotFoundError(f"Missing wiki template: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    headings = markdown_headings(text, level=2)
    return TemplateSpec(
        name=template_name,
        path=path,
        headings=headings,
        fields=template_fields(text),
    )


def template_for_page(page: Path) -> TemplateSpec | None:
    text = page.read_text(encoding="utf-8", errors="replace")
    frontmatter, _ = split_frontmatter(text)
    explicit = frontmatter.get("template")
    if explicit:
        name = explicit if explicit.endswith(".md") else f"{explicit}.md"
        return load_template(name)

    page_type = frontmatter.get("type", "").strip().lower()
    if page_type in {"faction-secret", "true-names"}:
        return load_template(TYPE_TO_TEMPLATE[page_type])

    try:
        rel = page.relative_to(WIKI_ROOT)
    except ValueError:
        return None
    if not rel.parts:
        return None
    top = rel.parts[0]
    if top in PATH_TO_TEMPLATE:
        return load_template(PATH_TO_TEMPLATE[top])
    if page_type in TYPE_TO_TEMPLATE:
        return load_template(TYPE_TO_TEMPLATE[page_type])
    return None


def check_page(page: Path) -> ConformanceResult | None:
    spec = template_for_page(page)
    if spec is None:
        return None

    text = page.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = split_frontmatter(text)
    headings = set(markdown_headings(body, level=2))

    missing_headings = tuple(h for h in spec.headings if h not in headings)
    missing_fields = tuple(f for f in spec.fields if f not in frontmatter)
    return ConformanceResult(
        page=page,
        template_name=spec.name,
        missing_headings=missing_headings,
        missing_fields=missing_fields,
        ok=not missing_headings and not missing_fields,
    )


def check_pages(pages: Iterable[Path]) -> list[ConformanceResult]:
    results: list[ConformanceResult] = []
    for page in pages:
        if page.name == "README.md" or "Templates" in page.parts or ".attic" in page.parts:
            continue
        if not page.exists() or page.suffix.lower() != ".md":
            continue
        result = check_page(page)
        if result is not None:
            results.append(result)
    return results


def render_report(results: list[ConformanceResult], scope_label: str) -> str:
    ok_count = sum(1 for r in results if r.ok)
    lines = [
        "---",
        "title: Template Conformance Report",
        "type: report",
        "visibility: player-safe",
        "updated: 2026-06-12",
        "---",
        "",
        "# Template Conformance Report",
        "",
        f"- Scope: **{scope_label}**",
        f"- Pages checked: **{len(results)}**",
        f"- Passing: **{ok_count}**",
        f"- Needs attention: **{len(results) - ok_count}**",
        "",
        "This report is generated by the session/wiki organization pipeline. It checks whether pages have the frontmatter fields and level-two headings expected by their wiki template.",
        "",
        "## Results",
        "",
    ]
    if not results:
        lines.append("_No template-managed pages checked._")
        return "\n".join(lines).rstrip() + "\n"

    for result in sorted(results, key=lambda r: str(r.page)):
        try:
            rel = result.page.relative_to(WIKI_ROOT)
        except ValueError:
            rel = result.page
        status = "OK" if result.ok else "Needs attention"
        lines.append(f"### {rel}")
        lines.append(f"- Status: **{status}**")
        lines.append(f"- Template: `{result.template_name}`")
        if result.missing_fields:
            lines.append(f"- Missing frontmatter: {', '.join(f'`{x}`' for x in result.missing_fields)}")
        if result.missing_headings:
            lines.append(f"- Missing headings: {', '.join(f'`{x}`' for x in result.missing_headings)}")
        if result.ok:
            lines.append("- Missing items: _None_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_conformance_report(pages: Iterable[Path], scope_label: str = "selected pages") -> Path:
    TEMPLATES_ROOT.mkdir(parents=True, exist_ok=True)
    results = check_pages(pages)
    CONFORMANCE_REPORT.write_text(render_report(results, scope_label), encoding="utf-8")
    return CONFORMANCE_REPORT


def main() -> None:
    pages = sorted(p for p in WIKI_ROOT.rglob("*.md") if ".git" not in p.parts)
    report = write_conformance_report(pages, scope_label="campaign wiki")
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
