#!/usr/bin/env python3
import difflib
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
AUDIT = P.memory_root / 'player_input' / 'request_audit.jsonl'
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


def append_audit_event(submission_id: str, payload: dict):
    if not submission_id:
        return
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    row = {'submission_id': submission_id, **payload}
    with AUDIT.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


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


def _append_history(r, event, detail=''):
    now = int(time.time())
    hist = r.get('history')
    if not isinstance(hist, list):
        hist = []
    hist.append({'ts': now, 'event': event, 'detail': detail})
    r['history'] = hist
    r['updated_at'] = now
    return now


def main():
    rows = load_queue()
    catalog = load_catalog()
    catalog_changed = False
    queue_changed = False
    processed = 0

    # normalize legacy status schema
    for r in rows:
        st = (r.get('status') or '').strip().lower()
        if st in {'researched', 'integrated'}:
            r['result'] = st
            r['status'] = 'completed'
            if 'completed_at' not in r:
                r['completed_at'] = int(r.get('researched_at') or r.get('ts') or time.time())
            if 'created_at' not in r:
                r['created_at'] = int(r.get('ts') or time.time())
            if 'updated_at' not in r:
                r['updated_at'] = r['completed_at']
            if not isinstance(r.get('history'), list):
                r['history'] = [{'ts': r['completed_at'], 'event': 'completed', 'detail': f'migrated legacy status={st}'}]
            queue_changed = True

    for r in rows:
        status = (r.get('status') or '').strip().lower()
        if status not in {'incoming', 'pending'}:
            continue
        entity = r.get('entity', '').strip()
        if not entity:
            continue

        # normalize legacy rows
        if 'created_at' not in r:
            r['created_at'] = int(r.get('ts') or time.time())
        _append_history(r, 'in_progress', 'queue processor started work')
        r['status'] = 'in_progress'
        r['started_at'] = r.get('started_at') or int(time.time())

        action_log = [
            'queue lookup',
            'entity canonicalization',
            'memory corpus mention scan (campaign logs + harmonized rules corpus)',
        ]
        submission_id = (r.get('source_submission_id') or '').strip()

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
            action_log.append('catalog entry created')

        mentions = find_mentions(terms)
        slug = slugify(canonical)
        canonical_article = CAMP_ENT / f'{slug}.md'
        out = REQ_ENT / f'{slug}.md'

        # If canonical campaign article exists, avoid duplicating a separate request dossier.
        if canonical_article.exists():
            if out.exists():
                out.unlink()
            r['status'] = 'completed'
            r['result'] = 'integrated'
            r['completed_at'] = int(time.time())
            r['resolved_entity'] = canonical
            r['output'] = str(canonical_article)
            _append_history(r, 'completed', 'already present in canonical campaign entities (integrated)')
            append_audit_event(submission_id, {
                'ts': int(time.time()),
                'status': 'completed',
                'result': 'integrated',
                'entity': canonical,
                'actions': action_log + ['existing entity dossier detected; no write needed'],
                'edited_docs': [],
            })
            queue_changed = True
            processed += 1
            continue

        lines = [
            f'# Campaign Entity Dossier: {canonical}',
            '',
            f"- Pipeline status: **researched_from_queue**",
            f"- Queue status at processing: **{status}**",
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

        before_text = out.read_text(encoding='utf-8', errors='replace') if out.exists() else ''
        after_text = '\n'.join(lines).rstrip() + '\n'
        out.write_text(after_text, encoding='utf-8')
        diff = ''.join(difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=str(out) + ':before',
            tofile=str(out) + ':after',
            n=3,
        ))

        r['status'] = 'completed'
        r['result'] = 'researched'
        r['researched_at'] = int(time.time())
        r['completed_at'] = int(time.time())
        r['resolved_entity'] = canonical
        r['output'] = str(out)
        _append_history(r, 'completed', f'research dossier written ({len(mentions)} mentions)')
        append_audit_event(submission_id, {
            'ts': int(time.time()),
            'status': 'completed',
            'result': 'researched',
            'entity': canonical,
            'actions': action_log + [f'request dossier generated ({len(mentions)} mentions)'],
            'edited_docs': [
                {
                    'path': str(out),
                    'change_type': 'create_or_update',
                    'diff': diff[:12000],
                }
            ],
        })
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
