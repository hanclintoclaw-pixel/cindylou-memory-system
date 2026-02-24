#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
MEMORY_ROOT = P.memory_root
RUN_NOTES = MEMORY_ROOT / "00_sources" / "run_notes"
WP_RUN_NOTES = MEMORY_ROOT / "wordpress_ingest" / "Run Notes"
OUT = MEMORY_ROOT / "10_consolidated" / "campaign" / "sessions"

DATE_RE = re.compile(r"(20\d{2})[-_/](\d{2})[-_/](\d{2})")


def norm_date(raw: str) -> str | None:
    m = DATE_RE.search(raw)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def file_fallback_date(path: Path) -> str | None:
    return norm_date(path.name)


def extract_chunks(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    chunks: list[dict] = []

    active_date: str | None = None
    active_start = 1
    buf: list[str] = []

    def flush(end_line: int):
        nonlocal buf, active_date, active_start
        content = "\n".join(buf).strip()
        if active_date and content:
            chunks.append({
                "date": active_date,
                "source": str(path),
                "start_line": active_start,
                "end_line": end_line,
                "content": content,
            })
        buf = []

    for i, line in enumerate(lines, start=1):
        s = line.strip()
        heading = s.startswith("#")
        inline_date = norm_date(s)

        if heading and inline_date:
            flush(i - 1)
            active_date = inline_date
            active_start = i + 1
            continue

        # If date appears in body and no active chunk date, start one.
        if inline_date and not active_date:
            active_date = inline_date
            active_start = i

        buf.append(line)

    flush(len(lines))

    # fallback: whole file mapped to filename date if no dated chunks found
    if not chunks:
        d = file_fallback_date(path)
        if d:
            content = text.strip()
            if content:
                chunks.append({
                    "date": d,
                    "source": str(path),
                    "start_line": 1,
                    "end_line": len(lines),
                    "content": content,
                })

    return chunks


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    note_files = []
    if RUN_NOTES.exists():
        note_files.extend(sorted(RUN_NOTES.glob("*.md")))
    if WP_RUN_NOTES.exists():
        note_files.extend(sorted(WP_RUN_NOTES.glob("*.md")))

    by_date: dict[str, list[dict]] = defaultdict(list)
    for f in note_files:
        for ch in extract_chunks(f):
            by_date[ch["date"]].append(ch)

    # write per-session files
    for d, items in sorted(by_date.items()):
        items.sort(key=lambda x: (x["source"], x["start_line"]))
        out = [
            f"# Campaign Session: {d}",
            "",
            f"- Source chunks: **{len(items)}**",
            "- Type: session-meta",
            "",
            "## Consolidated Notes",
            "",
        ]
        for idx, it in enumerate(items, start=1):
            src_name = Path(it["source"]).name
            out.append(f"### Chunk {idx} — {src_name} (L{it['start_line']}-L{it['end_line']})")
            out.append("")
            out.append(it["content"])
            out.append("")
            out.append(f"Source: `{src_name}`")
            out.append("")

        (OUT / f"{d}.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

    idx = [
        "# Campaign Sessions Index",
        "",
        f"- Sessions detected: **{len(by_date)}**",
        f"- Input files scanned: **{len(note_files)}**",
        "",
    ]
    for d in sorted(by_date):
        idx.append(f"- [{d}]({d}.md) — {len(by_date[d])} chunk(s)")

    (OUT / "SESSION_INDEX.md").write_text("\n".join(idx).rstrip() + "\n", encoding="utf-8")

    print(f"wrote sessions to: {OUT}")
    print(f"sessions detected: {len(by_date)}")


if __name__ == "__main__":
    main()
