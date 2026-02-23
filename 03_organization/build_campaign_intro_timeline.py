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


@dataclass
class IntroEvent:
    entity_display: str
    date_or_session: str
    text: str
    source_path: Path


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


def render_markdown(events: list[IntroEvent]) -> str:
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
    lines.extend(["```", ""])
    return "\n".join(lines)


def main():
    events = build_intro_events()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_markdown(events), encoding="utf-8")
    print(f"Wrote {len(events)} campaign introductions -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
