#!/usr/bin/env python3
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
QUEUE = P.memory_root / 'entity_request_queue.jsonl'
CAMP = P.memory_root / 'campaign'
CAMP_ENT = CAMP / 'entities'
REQ_ENT = CAMP / 'requests'
CATALOG = CAMP / 'entity_catalog.json'
CAMP_ENT.mkdir(parents=True, exist_ok=True)
REQ_ENT.mkdir(parents=True, exist_ok=True)
GAME_LOGS = P.raw_root / 'Game_Logs'
HARM = P.outputs_root / 'harmonized_all'
PAGE_RE = re.compile(r'^=====\s*PAGE\s+(\d+)\s*=====\s*$', re.MULTILINE)


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9-]+', '-', name.lower().replace('/', '-').replace(' ', '-')).strip('-')


def normalize(name: str) -> str:
    return re.sub(r'\s+', ' ', (name or '').strip()).casefold()


def parse_pages(text: str):
    ms = list(PAGE_RE.finditer(text))
    out = {}
    for i, m in enumerate(ms):
        p = int(m.group(1))
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out[p] = text[start:end]
    return out


def load_queue():
    rows = []
    if not QUEUE.exists():
        return rows
    for line in QUEUE.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def save_queue(rows):
    QUEUE.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + ('\n' if rows else ''), encoding='utf-8')


def load_catalog():
    if not CATALOG.exists():
        return []
    raw = json.loads(CATALOG.read_text(encoding='utf-8'))
    rows = raw.get('entities', []) if isinstance(raw, dict) else raw
    out = []
    for r in rows:
        canonical = (r.get('canonical') or '').strip()
        if not canonical:
            continue
        out.append({
            'canonical': canonical,
            'type': (r.get('type') or 'Unknown').strip(),
            'synonyms': [s.strip() for s in (r.get('synonyms') or []) if isinstance(s, str) and s.strip()],
        })
    return out


def save_catalog(rows):
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def resolve_canonical(entity: str, catalog):
    target = normalize(entity)
    for row in catalog:
        if normalize(row['canonical']) == target:
            return row
        for syn in row.get('synonyms', []):
            if normalize(syn) == target:
                return row
    return None


def find_mentions(terms, max_hits=120):
    pats = [re.compile(r'\b' + re.escape(t) + r'\b', re.IGNORECASE) for t in terms if t]
    hits = []
    seen = set()

    def line_hit(text):
        return any(p.search(text) for p in pats)

    for f in sorted(GAME_LOGS.glob('*.md')):
        lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
        for i, ln in enumerate(lines, start=1):
            if line_hit(ln):
                rec = {
                    'domain': 'campaign',
                    'source': f'{f}#L{i}',
                    'excerpt': ln.strip()[:280],
                }
                key = (rec['domain'], rec['source'], rec['excerpt'])
                if key in seen:
                    continue
                seen.add(key)
                hits.append(rec)
                if len(hits) >= max_hits:
                    return hits

    for h in sorted([p for p in HARM.glob('*') if p.is_dir()]):
        md = h / 'harmonized.md'
        if not md.exists():
            continue
        pages = parse_pages(md.read_text(encoding='utf-8', errors='replace'))
        for pno, txt in pages.items():
            if line_hit(txt):
                line = next((x.strip() for x in txt.splitlines() if line_hit(x)), txt.strip().splitlines()[0] if txt.strip() else '')
                rec = {
                    'domain': 'general',
                    'source': f'{md}#PAGE-{pno}',
                    'excerpt': line[:280],
                }
                key = (rec['domain'], rec['source'], rec['excerpt'])
                if key in seen:
                    continue
                seen.add(key)
                hits.append(rec)
                if len(hits) >= max_hits:
                    return hits
    return hits


def main():
    rows = load_queue()
    catalog = load_catalog()
    catalog_changed = False
    queue_changed = False
    processed = 0

    for r in rows:
        if r.get('status') != 'pending':
            continue
        entity = r.get('entity', '').strip()
        if not entity:
            continue

        match = resolve_canonical(entity, catalog)
        if match:
            canonical = match['canonical']
            terms = [canonical] + match.get('synonyms', [])
        else:
            canonical = entity
            terms = [entity]
            catalog.append({'canonical': canonical, 'type': 'Unknown', 'synonyms': []})
            catalog_changed = True
            match = catalog[-1]

        mentions = find_mentions(terms)
        slug = slugify(canonical)
        canonical_article = CAMP_ENT / f'{slug}.md'
        out = REQ_ENT / f'{slug}.md'

        # If canonical campaign article exists, avoid duplicating a separate request dossier.
        if canonical_article.exists():
            if out.exists():
                out.unlink()
            r['status'] = 'integrated'
            r['researched_at'] = time.time()
            r['resolved_entity'] = canonical
            r['output'] = str(canonical_article)
            queue_changed = True
            processed += 1
            continue

        lines = [
            f'# Campaign Entity Dossier: {canonical}',
            '',
            f"- Pipeline status: **researched_from_queue**",
            f"- Queue status at processing: **{r.get('status', 'pending')}**",
            f'- Entity type: **{match.get("type", "Unknown")}**',
            f"- Synonyms: {', '.join(match.get('synonyms', [])) if match.get('synonyms') else '_None_'}",
            f'- Requested as: **{entity}**',
            f'- Mentions found: **{len(mentions)}**',
            '',
        ]
        if r.get('note'):
            lines += [f"- Request note: {r['note']}", '']
        lines += ['## Cited Mentions', '']
        if not mentions:
            lines.append('_No mentions found yet._')
        for m in mentions:
            lines.append(f"- **{m['domain']}** - {m['excerpt']}")
            lines.append(f"  - Source: `{m['source']}`")
        out.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

        r['status'] = 'researched'
        r['researched_at'] = time.time()
        r['resolved_entity'] = canonical
        r['output'] = str(out)
        queue_changed = True
        processed += 1

    if queue_changed:
        save_queue(rows)
    if catalog_changed:
        save_catalog(catalog)
    print('processed', processed)
    if catalog_changed:
        print('updated', CATALOG)


if __name__ == '__main__':
    main()
