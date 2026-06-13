#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[1]
for import_root in (SCRIPT_DIR, REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from config.pipeline_paths import get_paths
from build_campaign_intro_timeline import summarize_session_text
from wiki_templates import write_conformance_report

P = get_paths()
MEMORY_ROOT = P.cleaned_root / 'memory'
SESSIONS_ROOT = MEMORY_ROOT / '10_consolidated' / 'campaign' / 'sessions'
CURATED_SUMMARIES_ROOT = MEMORY_ROOT / '10_consolidated' / 'campaign' / 'session_summaries'
WIKI_ROOT = P.code_root / 'campaign-wiki'
WIKI_SESSIONS = WIKI_ROOT / 'Sessions'
README_PATH = WIKI_SESSIONS / 'README.md'


def curated_summary(date: str) -> str | None:
    p = CURATED_SUMMARIES_ROOT / f'{date}.md'
    if not p.exists():
        return None
    text = p.read_text(encoding='utf-8', errors='replace')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith('#')]
    return ' '.join(lines).strip() or None


def extract_source_refs(session_text: str) -> list[str]:
    refs: list[str] = []
    seen = set()
    for raw in session_text.splitlines():
        m = re.search(r'Source:\s*`([^`]+)`', raw)
        if not m:
            continue
        ref = m.group(1).strip()
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def session_page(date: str, session_path: Path, summary: str, refs: list[str]) -> str:
    title = f'Session {date}'
    sources = [str(session_path)] + refs
    source_lines = '\n'.join(f'  - {src}' for src in sources)
    return f'''---
title: {title}
type: session
template: Session
visibility: player-safe
session_date: {date}
in_world_date: {date}
updated: {date}
tags: [session]
participants: []
sources:
{source_lines}
---

# {title}

## Summary

{summary}

## Participants

_Pending deeper extraction from cleaned notes._

## Key Events

_Pending deeper extraction from cleaned notes._

## Discoveries

_Pending deeper extraction from cleaned notes._

## Consequences

_Pending deeper extraction from cleaned notes._

## Updated Pages

_Pending deeper extraction from cleaned notes._

## Open Questions

_Pending deeper extraction from cleaned notes._

## Sources

''' + '\n'.join(f'- `{src}`' for src in sources) + '\n'


def rebuild_readme() -> None:
    pages = sorted(p for p in WIKI_SESSIONS.glob('*.md') if p.name not in {'README.md', 'ARCHIVE_TRIAGE.md', 'ARCHIVE_ANALYSIS.md'})
    session_pages = []
    for p in pages:
        m = re.match(r'(\d{4}-\d{2}-\d{2})\.md$', p.name)
        if m:
            session_pages.append((m.group(1), p.name))
    session_pages.sort(key=lambda x: x[0])

    lines = [
        '# Sessions',
        '',
        '> Mixed-date warning: some session page slugs are **real-world played dates** and some are **in-world Shadowrun dates**. For the reconciled two-column chronology, use [Timeline / Session Chronology](../Timeline/Session-Chronology.md).',
        '',
    ]
    for date, name in session_pages:
        lines.append(f'- [Session {date}]({name})')
    lines.extend([
        '',
        '## Archive analysis',
        '',
        '- [Archive triage notes](ARCHIVE_TRIAGE.md)',
        '- [Session archive analysis](ARCHIVE_ANALYSIS.md)',
        '- [Campaign arc index](../Timeline/Arc-Index.md)',
        '',
        '## Related reference layers',
        '',
        '- [NPC index](../NPCs/README.md)',
        '- [Faction pages](../Factions/)',
        '- [Organization pages](../Organizations/README.md)',
        '- [Recaps](../Recaps/README.md)',
        '- [Tech notes](../Tech/README.md)',
    ])
    README_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    WIKI_SESSIONS.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0
    touched_pages: list[Path] = []
    for p in sorted(SESSIONS_ROOT.glob('*.md')):
        if p.name.upper() == 'SESSION_INDEX.MD':
            continue
        m = re.match(r'(\d{4}-\d{2}-\d{2})\.md$', p.name)
        if not m:
            continue
        date = m.group(1)
        target = WIKI_SESSIONS / p.name
        if target.exists():
            skipped += 1
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        summary = curated_summary(date) or summarize_session_text(text)
        refs = extract_source_refs(text)
        target.write_text(session_page(date, p, summary, refs), encoding='utf-8')
        touched_pages.append(target)
        created += 1
    rebuild_readme()
    report = write_conformance_report(touched_pages, scope_label='newly exported session pages') if touched_pages else None
    print(f'created {created} wiki session page(s), skipped {skipped} existing pages')
    print(f'updated {README_PATH}')
    if report:
        print(f'updated {report}')
    else:
        print('template conformance report unchanged (no new session pages)')


if __name__ == '__main__':
    main()
