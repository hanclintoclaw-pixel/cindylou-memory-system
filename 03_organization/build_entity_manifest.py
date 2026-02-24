#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
MEMORY_ROOT = Path(str(P.cleaned_root / 'memory'))
CONSOLIDATED_ROOT = MEMORY_ROOT / '10_consolidated'
OUT = CONSOLIDATED_ROOT / 'entity_manifest.jsonl'


def collect(scope: str, root: Path):
    rows = []
    if not root.exists():
        return rows
    groups = {}
    for f in root.iterdir():
        if not f.is_file():
            continue
        if f.suffix not in {'.md', '.jsonl'}:
            continue
        base = f.name.split('.', 1)[0]
        groups.setdefault(base, []).append(f)

    for entity, files in sorted(groups.items()):
        md_paths = [f for f in files if f.suffix == '.md']
        # If subsection files exist (<entity>.<section>.md), prefer those and skip the legacy monolith (<entity>.md)
        has_subsections = any(f.name.count('.') >= 2 for f in md_paths)
        if has_subsections:
            md_paths = [f for f in md_paths if f.stem != entity]
        md_files = sorted([str(f) for f in md_paths], key=lambda s: Path(s).name.lower())
        jsonl_files = sorted([str(f) for f in files if f.suffix == '.jsonl'], key=lambda s: Path(s).name.lower())
        if not md_files and not jsonl_files:
            continue
        rows.append({
            'entity': entity,
            'scope': scope,
            'md_files': md_files,
            'jsonl_files': jsonl_files,
        })
    return rows


def norm_entity_key(name: str) -> str:
    s = (name or '').strip().lower()
    s = re.sub(r'^entity\s*:\s*', '', s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    campaign_rows = collect('campaign', CONSOLIDATED_ROOT / 'campaign' / 'entities')
    general_rows = collect('general', CONSOLIDATED_ROOT / 'general' / 'entities')

    general_keys = {norm_entity_key(r['entity']) for r in general_rows}
    filtered_campaign = [r for r in campaign_rows if norm_entity_key(r['entity']) not in general_keys]

    rows = filtered_campaign + general_rows

    with OUT.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    skipped = len(campaign_rows) - len(filtered_campaign)
    print(f'wrote {len(rows)} rows -> {OUT} (skipped {skipped} campaign duplicates with general scope)')


if __name__ == '__main__':
    main()
