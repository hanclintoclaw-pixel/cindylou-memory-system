#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
MEMORY_ROOT = P.cleaned_root / "memory"
MANIFEST_PATH = MEMORY_ROOT / "10_consolidated" / "entity_manifest.jsonl"
OUTPUT_PATH = MEMORY_ROOT / "90_derived" / "CAMPAIGN_INTRO_TIMELINE.md"
SESSIONS_ROOT = MEMORY_ROOT / "10_consolidated" / "campaign" / "sessions"
RUN_NOTES_ROOT = MEMORY_ROOT / "00_sources" / "run_notes"
WP_RUN_NOTES_ROOT = MEMORY_ROOT / "wordpress_ingest" / "Run Notes"


@dataclass
class IntroEvent:
    entity_display: str
    date_or_session: str
    text: str
    source_path: Path


@dataclass
class SessionEvent:
    date: str
    summary: str
    source_path: Path
    source_refs: list[str]


def display_name(entity_slug: str) -> str:
    label = re.sub(r"[-_]+", " ", (entity_slug or "").strip())
    label = re.sub(r"\s+", " ", label).strip()
    return label.title() if label else "Unknown Entity"


def normalize_text(raw: str, limit: int = 80) -> str:
    text = (raw or "").replace("\ufeff", " ")
    text = re.sub(r"[*_`#>\-\u2022]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "first campaign mention"
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rsplit(" ", 1)[0].strip()
    return (clipped or text[: limit - 1]).rstrip(" ,;:.") + "…"


def manifest_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing manifest: {path}")
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def first_timeline_event(timeline_path: Path) -> dict | None:
    if not timeline_path.exists():
        return None
    for raw in timeline_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def pick_timeline_file(row: dict) -> Path | None:
    for raw_path in row.get("jsonl_files", []):
        candidate = Path(str(raw_path))
        if candidate.name.endswith(".timeline.jsonl"):
            return candidate
    return None


def sort_key(event: IntroEvent):
    key = event.date_or_session.strip()
    try:
        return (0, datetime.strptime(key, "%Y-%m-%d"), event.entity_display.lower())
    except ValueError:
        return (1, key.lower(), event.entity_display.lower())


def build_intro_events() -> list[IntroEvent]:
    events: list[IntroEvent] = []
    for row in manifest_rows(MANIFEST_PATH):
        if str(row.get("scope", "")).strip().lower() != "campaign":
            continue
        entity_slug = str(row.get("entity", "")).strip()
        if not entity_slug:
            continue
        timeline_path = pick_timeline_file(row)
        if not timeline_path:
            continue
        first = first_timeline_event(timeline_path)
        if not first:
            continue
        date_or_session = str(first.get("date_or_session") or "unspecified").strip() or "unspecified"
        short_text = normalize_text(str(first.get("text") or ""))
        events.append(
            IntroEvent(
                entity_display=display_name(entity_slug),
                date_or_session=date_or_session,
                text=short_text,
                source_path=timeline_path,
            )
        )
    events.sort(key=sort_key)
    return events


def _sanitize_mermaid_text(text: str) -> str:
    # Mermaid timeline is picky; keep summaries plain and punctuation-light.
    out = text
    out = out.replace(":", " -")
    out = out.replace(";", " -")
    out = out.replace('"', "")
    out = out.replace("`", "")
    out = re.sub(r"[{}\[\]()<>]", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def summarize_session_text(md_text: str) -> str:
    lines = [ln.strip() for ln in md_text.splitlines()]
    blacklist = (
        "#",
        "##",
        "###",
        "- source chunks:",
        "- type:",
        "source:",
        "## consolidated notes",
        "chunk",
    )
    candidates: list[str] = []
    for line in lines:
        if not line:
            continue
        low = line.lower()
        if any(low.startswith(b) for b in blacklist):
            continue
        if len(line) < 20:
            continue
        candidates.append(line)

    if not candidates:
        return "Session notes available; summary pending refinement."

    # Build a short guessed summary from top 1-2 meaningful lines.
    first = _sanitize_mermaid_text(normalize_text(candidates[0], limit=90))
    if len(candidates) > 1:
        second = _sanitize_mermaid_text(normalize_text(candidates[1], limit=70))
        if second.lower() not in first.lower():
            return _sanitize_mermaid_text(normalize_text(f"{first} - {second}", limit=120))
    return first


def _source_lookup() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for root in [RUN_NOTES_ROOT, WP_RUN_NOTES_ROOT]:
        if not root.exists():
            continue
        for p in root.glob("*.md"):
            out[p.name] = p
    return out


def _extract_source_refs(session_text: str, src_map: dict[str, Path]) -> list[str]:
    refs: list[str] = []
    seen = set()
    for raw in session_text.splitlines():
        s = raw.strip()
        m = re.search(r"Source:\s*`([^`]+)`", s)
        if not m:
            continue
        src_name = Path(m.group(1).strip()).name
        full = src_map.get(src_name)
        ref = str(full) if full else src_name
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def build_session_events() -> list[SessionEvent]:
    events: list[SessionEvent] = []
    if not SESSIONS_ROOT.exists():
        return events

    src_map = _source_lookup()

    for p in sorted(SESSIONS_ROOT.glob("*.md")):
        if p.name.upper() == "SESSION_INDEX.MD":
            continue
        m = re.match(r"(20\d{2}-\d{2}-\d{2})\.md$", p.name)
        if not m:
            continue
        date = m.group(1)
        text = p.read_text(encoding="utf-8", errors="replace")
        events.append(
            SessionEvent(
                date=date,
                summary=summarize_session_text(text),
                source_path=p,
                source_refs=_extract_source_refs(text, src_map),
            )
        )

    events.sort(key=lambda e: e.date)
    return events


def render_markdown(events: list[IntroEvent], sessions: list[SessionEvent]) -> str:
    lines = [
        "# Campaign First Introductions Timeline",
        "",
        "Generated from the first row of each campaign entity `*.timeline.jsonl` file listed in `entity_manifest.jsonl`.",
        "",
        "```mermaid",
        "timeline",
        "    title Campaign First Introductions",
    ]
    for event in events:
        lines.append(f"    {event.date_or_session} : {event.entity_display}: {event.text}")
    lines.extend(["```", "", "## Session Timeline (guessed summaries)", "", "Built from `10_consolidated/campaign/sessions/*.md`.", "", "```mermaid", "timeline", "    title Campaign Sessions"])
    for sess in sessions:
        lines.append(f"    {sess.date} : {sess.summary}")
    lines.extend(["```", "", "## Session Sources", "", "Click-through references for each session timeline entry.", ""])
    for sess in sessions:
        lines.append(f"### {sess.date}")
        lines.append(f"- Session file: `{sess.source_path}`")
        if not sess.source_refs:
            lines.append("- Sources: _none detected_")
        else:
            lines.append("- Sources:")
            for ref in sess.source_refs:
                lines.append(f"  - `{ref}`")
        lines.append("")
    return "\n".join(lines)


def main():
    events = build_intro_events()
    sessions = build_session_events()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_markdown(events, sessions), encoding="utf-8")
    print(f"Wrote {len(events)} campaign introductions + {len(sessions)} sessions -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
