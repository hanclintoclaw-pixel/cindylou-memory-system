#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
GAME_LOGS = P.raw_root / 'Game_Logs'
WP_RUN_NOTES = P.memory_root / 'wordpress_ingest' / 'Run Notes'
PLAYER_INPUT_FILE = P.memory_root / 'player_input' / 'submissions.jsonl'
OUT = P.memory_root / 'campaign'
ENT = OUT / 'entities'
CATALOG = OUT / 'entity_catalog.json'
OUT.mkdir(parents=True, exist_ok=True)
ENT.mkdir(parents=True, exist_ok=True)

DEATH_HINTS = re.compile(r'\b(died|dead|killed|slain|passed away|deceased|death)\b', re.IGNORECASE)
ALIVE_HINTS = re.compile(r'\b(alive|survived|returns?|back again|still active|still around)\b', re.IGNORECASE)


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9-]+', '-', name.lower().replace('/', '-').replace(' ', '-')).strip('-')


def extract_session_title(path: Path):
    m = re.search(r'(\d{4}[-_]\d{2}[-_]\d{2})', path.name)
    return m.group(1).replace('_', '-') if m else path.stem


def load_catalog(path: Path):
    if not path.exists():
        raise FileNotFoundError(f'Missing entity catalog: {path}')
    raw = json.loads(path.read_text(encoding='utf-8'))
    rows = raw.get('entities', []) if isinstance(raw, dict) else raw

    catalog = []
    for row in rows:
        canonical = (row.get('canonical') or '').strip()
        if not canonical:
            continue
        etype = (row.get('type') or 'Unclassified').strip()
        synonyms = [s.strip() for s in (row.get('synonyms') or []) if isinstance(s, str) and s.strip()]
        catalog.append({'canonical': canonical, 'type': etype, 'synonyms': synonyms})
    return catalog


def build_alias_patterns(catalog):
    aliases = []
    for row in catalog:
        for val in [row['canonical']] + row['synonyms']:
            aliases.append((val, row['canonical']))
    aliases.sort(key=lambda x: len(x[0]), reverse=True)

    seen = set()
    pats = []
    for alias, canonical in aliases:
        key = alias.lower()
        if key in seen:
            continue
        seen.add(key)
        pats.append((canonical, re.compile(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', re.IGNORECASE)))
    return pats


def group_name(entity_type: str) -> str:
    t = (entity_type or '').strip().upper()
    if t == 'PC':
        return 'PCs'
    if t == 'NPC':
        return 'NPCs'
    return 'Unclassified'


def entity_heading(entity_type: str, canonical: str) -> str:
    t = (entity_type or '').strip().upper()
    if t == 'PC':
        return f'# Campaign PC: {canonical}'
    if t == 'NPC':
        return f'# Campaign NPC: {canonical}'
    return f'# Campaign Entity: {canonical}'


def extract_facets(refs: list[dict]):
    facets = {
        'physical': ['looks', 'appearance', 'tall', 'short', 'hair', 'eyes', 'face', 'tattoo', 'scar'],
        'capabilities': ['can ', 'able to', 'skill', 'hacking', 'deck', 'combat', 'spell', 'drone', 'pilot'],
        'quirks': ['weird', 'odd', 'meme', 'quirk', 'obsess', 'habit', 'insane', 'eccentric'],
        'equipment': ['deck', 'gun', 'shotgun', 'sword', 'armor', 'vehicle', 'drone', 'transceiver', 'gear'],
    }
    out = {k: [] for k in facets}
    for r in refs:
        t = r['text']
        low = t.lower()
        for k, keys in facets.items():
            if len(out[k]) >= 3:
                continue
            if any(x in low for x in keys):
                src = f"{r['source_file']}#L{r['line']}"
                if not any(e['text'] == t for e in out[k]):
                    out[k].append({'text': t, 'source': src})
    return out


def detect_continuity_notes(refs: list[dict]):
    notes = []
    death_refs = [r for r in refs if DEATH_HINTS.search(r['text'])]
    alive_refs = [r for r in refs if ALIVE_HINTS.search(r['text'])]
    if death_refs and alive_refs:
        d = death_refs[0]
        a = alive_refs[0]
        notes.append({
            'text': 'Possible continuity contradiction: death/defeat language appears alongside later/alternate survival language.',
            'sources': [f"{d['source_file']}#L{d['line']}", f"{a['source_file']}#L{a['line']}"]
        })
    return notes


def summarize_entity(canonical: str, refs: list[dict], entity_type: str):
    if not refs:
        return {
            'description': f'{canonical} has no cited campaign references yet.',
            'summary': f'{canonical} currently has insufficient campaign data for a reliable profile.',
            'opinion': "Cindy's take: still a mystery. I'd keep this one on my watchlist until we gather more intel.",
            'timeline': [],
            'notable': [],
            'passing': None,
        }

    first = refs[0]
    texts = ' '.join(r['text'] for r in refs).lower()

    tags = []
    if any(k in texts for k in ['matrix', 'host', 'deck', 'security', 'network']):
        tags.append('matrix-active')
    if any(k in texts for k in ['drone', 'vehicle', 'rig', 'vcr']):
        tags.append('field-tech')
    if any(k in texts for k in ['contact', 'deal', 'negotiat', 'introduce', 'ask']):
        tags.append('social-connector')
    if any(k in texts for k in ['attack', 'fight', 'shot', 'combat', 'gun', 'sword']):
        tags.append('combat-capable')

    description = (
        f"{canonical} is a {' and '.join(tags) if tags else 'recurring'} campaign figure "
        f"first cited in {first['session']}."
    )
    summary = (
        f"Across {len(refs)} cited mentions, {canonical} appears as a consistent participant in key run-time decisions "
        f"and scene-level developments."
    )

    et = (entity_type or '').upper()
    if len(refs) < 2:
        opinion = 'Insufficient data for a meaningful opinion.'
    elif et == 'PC':
        if 'matrix-active' in tags:
            opinion = f"Cindy's take: {canonical} brings useful matrix-adjacent instincts and tends to make the team faster at decision time."
        elif 'combat-capable' in tags:
            opinion = f"Cindy's take: {canonical} reads like an execution specialist — strongest when plans are concrete and tempo stays high."
        else:
            opinion = f"Cindy's take: {canonical} feels like dependable table glue; not always loud, but consistently relevant when pressure rises."
    elif et == 'NPC':
        if 'social-connector' in tags:
            opinion = f"Cindy's take: {canonical} behaves like a leverage node — relationship management around them has outsized payoff."
        elif 'matrix-active' in tags:
            opinion = f"Cindy's take: {canonical} should be treated as strategically significant infrastructure, not background flavor."
        else:
            opinion = f"Cindy's take: {canonical} is a situational power broker; I would approach with careful calibration, not blunt asks."
    else:
        opinion = f"Cindy's take: {canonical} is still under-modeled. I can track patterns, but confidence is not yet high."

    timeline = []
    for r in refs[:6]:
        timeline.append({
            'session': r['session'],
            'text': r['text'],
            'source': f"{r['source_file']}#L{r['line']}",
        })

    notable = []
    seen = set()
    for r in refs:
        txt = r['text']
        if len(notable) >= 5:
            break
        if txt in seen:
            continue
        if any(k in txt.lower() for k in ['attack', 'run', 'mission', 'contact', 'plan', 'host', 'matrix', 'drone', 'fed', 'mayor', 'deal', 'conflict']):
            notable.append({
                'session': r['session'],
                'text': txt,
                'source': f"{r['source_file']}#L{r['line']}",
            })
            seen.add(txt)

    passing = None
    for r in refs:
        if DEATH_HINTS.search(r['text']):
            passing = {
                'session': r['session'],
                'text': r['text'],
                'source': f"{r['source_file']}#L{r['line']}",
            }
            break

    return {
        'description': description,
        'summary': summary,
        'opinion': opinion,
        'timeline': timeline,
        'notable': notable,
        'passing': passing,
        'facets': extract_facets(refs),
        'continuity': detect_continuity_notes(refs),
    }


def main():
    catalog = load_catalog(CATALOG)
    patterns = build_alias_patterns(catalog)
    logs = sorted(GAME_LOGS.glob('*.md'))
    wp_logs = sorted(WP_RUN_NOTES.glob('*.md')) if WP_RUN_NOTES.exists() else []

    entries = []
    entity_refs = {row['canonical']: [] for row in catalog}
    entity_meta = {row['canonical']: row for row in catalog}

    player_inputs = []
    if PLAYER_INPUT_FILE.exists():
        for line in PLAYER_INPUT_FILE.read_text(encoding='utf-8', errors='replace').splitlines():
            if not line.strip():
                continue
            try:
                player_inputs.append(json.loads(line))
            except Exception:
                continue

    for f in logs + wp_logs:
        txt = f.read_text(encoding='utf-8', errors='replace')
        session = extract_session_title(f)
        for i, line in enumerate(txt.splitlines(), start=1):
            s = line.strip()
            if len(s) < 25:
                continue
            hits = []
            for canonical, pat in patterns:
                if pat.search(s) and canonical not in hits:
                    hits.append(canonical)
            if not hits:
                continue

            rec = {'session': session, 'source_file': str(f), 'line': i, 'text': s[:320], 'entities': hits}
            entries.append(rec)
            for c in hits:
                entity_refs[c].append(rec)

    # Player-input submissions behave like campaign notes with explicit attribution.
    for i, item in enumerate(player_inputs, start=1):
        txt = (item.get('note') or '').strip()
        if len(txt) < 8:
            continue
        entity_hint = (item.get('entity') or '').strip().lower()
        player = (item.get('player') or 'Unknown Player').strip()
        date = (item.get('date') or 'undated').strip()

        hits = []
        for canonical, pat in patterns:
            if pat.search(txt) and canonical not in hits:
                hits.append(canonical)
        for canonical in entity_refs.keys():
            if canonical.lower() == entity_hint and canonical not in hits:
                hits.append(canonical)

        if not hits:
            continue

        rec = {
            'session': f'Player Input ({date})',
            'source_file': str(PLAYER_INPUT_FILE),
            'line': i,
            'text': f"[{player}] {txt}"[:320],
            'entities': hits,
        }
        entries.append(rec)
        for c in hits:
            entity_refs[c].append(rec)

    idx_md = OUT / 'CAMPAIGN_INDEX.md'
    lines = [
        '# Campaign Knowledge Index',
        '',
        f'- Source folders: `{GAME_LOGS}` and `{WP_RUN_NOTES}`',
        f'- Notes scanned: **{len(logs) + len(wp_logs)}**',
        f'- Cited campaign facts: **{len(entries)}**',
        f'- Entities in catalog: **{len(catalog)}**',
        '- Scope: campaign-only entities (run notes). General SR3 lore stays under `memory/lore`.',
        '',
        '## Entity Coverage',
        '',
    ]

    groups = {'PCs': [], 'NPCs': [], 'Unclassified': []}
    for canonical, refs in entity_refs.items():
        groups[group_name(entity_meta[canonical].get('type', 'Unclassified'))].append((canonical, refs))

    for grp in ['PCs', 'NPCs', 'Unclassified']:
        items = groups[grp]
        lines.append(f'### {grp} ({len(items)})')
        if not items:
            lines.append('- _None_')
            lines.append('')
            continue
        for canonical, refs in sorted(items, key=lambda x: len(x[1]), reverse=True):
            slug = slugify(canonical)
            lines.append(f'- **{canonical}** — {len(refs)} citations (`entities/{slug}.md`)')
        lines.append('')

    idx_md.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    for canonical, refs in entity_refs.items():
        meta = entity_meta[canonical]
        slug = slugify(canonical)
        p = ENT / f'{slug}.md'
        syn = ', '.join(meta['synonyms']) if meta['synonyms'] else '_None_'
        agg = summarize_entity(canonical, refs, meta.get('type', 'Unclassified'))

        ref_map = {}
        ref_list = []

        def cite(source: str) -> str:
            if source not in ref_map:
                ref_map[source] = len(ref_map) + 1
                ref_list.append(source)
            n = ref_map[source]
            return f"<a href='#ref-{n}'>[[{n}]]</a>"

        out = [
            entity_heading(meta.get('type', 'Unclassified'), canonical),
            '',
            f"- Entity type: **{meta.get('type', 'Unclassified')}**",
            f'- Synonyms: {syn}',
            f'- Citation count: **{len(refs)}**',
            '',
            '## Description',
            '',
            f"{agg['description']}",
            '',
            '## Summary',
            '',
            f"{agg['summary']}",
            '',
            "## Cindy's Opinion",
            '',
            f"{agg['opinion']}",
            '',
            '## Profile facets',
            '',
        ]

        facets = agg.get('facets', {})
        label_map = {
            'physical': 'Physical description',
            'capabilities': 'Capabilities',
            'quirks': 'Quirks',
            'equipment': 'Equipment',
        }
        for key in ['physical', 'capabilities', 'quirks', 'equipment']:
            out.append(f"### {label_map[key]}")
            vals = facets.get(key, [])
            if not vals:
                out.append('_Not clearly established in current notes._')
            else:
                for ev in vals:
                    c = cite(ev['source'])
                    out.append(f"- {ev['text']} {c}")
            out.append('')

        out += ['## Timeline (abbreviated)', '']

        if not agg['timeline']:
            out.append('_No timeline events yet._')
        for ev in agg['timeline']:
            c = cite(ev['source'])
            out.append(f"- **{ev['session']}** — {ev['text']} {c}")

        out += ['', '## Notable events', '']
        if not agg['notable']:
            out.append('_No notable events identified yet._')
        for ev in agg['notable']:
            c = cite(ev['source'])
            out.append(f"- {ev['text']} {c}")

        out += ['', '## Passing / death record', '']
        if agg['passing']:
            c = cite(agg['passing']['source'])
            out.append(f"- {agg['passing']['text']} {c}")
        else:
            out.append('_No confirmed passing/death reference found in current notes._')

        out += ['', '## Continuity notes', '']
        cont = agg.get('continuity', [])
        if not cont:
            out.append('_No major continuity conflicts detected in current notes._')
        else:
            for n in cont:
                cites = ' '.join(cite(s) for s in n.get('sources', []))
                out.append(f"- {n['text']} {cites}")

        out += ['', '## References', '']
        if not ref_list:
            out.append('_No references recorded._')
        else:
            for i, src in enumerate(ref_list, start=1):
                out.append(f"- <a id='ref-{i}'></a> [{i}] `{src}`")

        p.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')

    payload = {
        'scope': 'campaign_only',
        'entities': {
            c: {
                'type': entity_meta[c].get('type', 'Unclassified'),
                'synonyms': entity_meta[c].get('synonyms', []),
                'citation_count': len(refs),
            }
            for c, refs in entity_refs.items()
        }
    }
    (OUT / 'index.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('wrote', idx_md)
    print('wrote', OUT / 'index.json')


if __name__ == '__main__':
    main()
