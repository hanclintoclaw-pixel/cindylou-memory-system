#!/usr/bin/env python3
import json
import re
from pathlib import Path

WS = Path('/Users/hanclaw/.openclaw/workspace-cindylou')
HARM = WS / 'outputs' / 'harmonized_all'
MEM_TOPICS = WS / 'memory' / 'topics'
MEM_TOPICS.mkdir(parents=True, exist_ok=True)

PAGE_RE = re.compile(r'^=====\s*PAGE\s+(\d+)\s*=====\s*$', re.MULTILINE)

TOPIC_RULES = {
    'matrix': [r'\bmatrix\b', r'\bdeck\w*\b', r'\bdecker\b', r'\bhost\b', r'\bpersona\b', r'\bic\b', r'\bice\b'],
    'combat': [r'\bcombat\b', r'\binitiative\b', r'\bdamage\b', r'\barmor\b', r'\battack\b'],
    'magic': [r'\bmagic\b', r'\bspell\w*\b', r'\badept\b', r'\bconjur\w*\b', r'\bdrain\b'],
    'rigging': [r'\brigg\w*\b', r'\bvehicle\b', r'\bdrones?\b', r'\bvcr\b'],
    'cyberware_bioware': [r'\bcyber\w*\b', r'\bbioware\b', r'\bessence\b'],
    'gear_equipment': [r'\bweapon\w*\b', r'\bgear\b', r'\bequipment\b', r'\butilit(?:y|ies)\b'],
}


def parse_pages(text: str):
    matches = list(PAGE_RE.finditer(text))
    pages = {}
    for i, m in enumerate(matches):
        p = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        pages[p] = text[start:end].strip()
    return pages


def snippets(page_text, max_snips=2):
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    out = []
    for ln in lines:
        if len(ln) > 20:
            out.append(ln[:220])
        if len(out) >= max_snips:
            break
    return out


def count_hits(text, patterns):
    return sum(len(re.findall(p, text, flags=re.IGNORECASE)) for p in patterns)


books = sorted([p for p in HARM.glob('*') if p.is_dir()])
index = {k: [] for k in TOPIC_RULES}

for book_dir in books:
    hfile = book_dir / 'harmonized.md'
    if not hfile.exists():
        continue
    pages = parse_pages(hfile.read_text(encoding='utf-8', errors='replace'))

    for page_no, page_text in pages.items():
        lower = page_text.lower()
        for topic, pats in TOPIC_RULES.items():
            hits = count_hits(lower, pats)
            if hits > 0:
                index[topic].append({
                    'book': book_dir.name,
                    'source': str(hfile),
                    'page': page_no,
                    'hits': hits,
                    'snippets': snippets(page_text),
                })

# scoring
book_total = max(len(books), 1)
topic_hit_totals = {t: sum(it['hits'] for it in items) for t, items in index.items()}
max_hits = max(topic_hit_totals.values()) if topic_hit_totals else 1
scores = {}

for topic, items in index.items():
    covered_books = len(set(it['book'] for it in items))
    coverage = covered_books / book_total
    hit_ratio = topic_hit_totals[topic] / max_hits if max_hits else 0
    score = round((0.6 * coverage + 0.4 * hit_ratio) * 100, 1)
    scores[topic] = {
        'score': score,
        'coverage_books': covered_books,
        'coverage_total_books': book_total,
        'total_hits': topic_hit_totals[topic],
        'citation_count': len(items),
    }

for topic, items in index.items():
    out = MEM_TOPICS / f'{topic}.md'
    m = scores[topic]
    lines = [
        f'# SR3 Topic: {topic}',
        '',
        f"- Topic reference score: **{m['score']} / 100**",
        f"- Coverage: **{m['coverage_books']} / {m['coverage_total_books']} manuals**",
        f"- Total keyword hits: **{m['total_hits']}**",
        f"- Citation count: **{m['citation_count']}**",
        '',
        '## Referenced Knowledge (with citations)',
        '',
    ]
    for it in sorted(items, key=lambda x: (x['book'], x['page'])):
        lines.append(f"### {it['book']} — page {it['page']} (hits: {it['hits']})")
        lines.append(f"Source manual: `{it['book']}`")
        lines.append(f"Source file: `{it['source']}`")
        for s in it['snippets']:
            lines.append(f"- {s}")
        lines.append('')
    if not items:
        lines.append('_No matched material yet._')
    out.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

summary = MEM_TOPICS / 'TOPIC_SCORES_SUMMARY.md'
summary_lines = [
    '# SR3 Knowledge Topic Score Summary',
    '',
    f'- Source corpus: `{HARM}`',
    f'- Manuals scanned: **{book_total}**',
    '- Score formula: `0.6 * coverage_ratio + 0.4 * hit_ratio` (scaled to 100)',
    '- Citation rule: every knowledge item includes source manual + page number.',
    '',
    '## Topic Scores',
    ''
]
for topic, meta in sorted(scores.items(), key=lambda kv: kv[1]['score'], reverse=True):
    summary_lines.append(
        f"- **{topic}** — score **{meta['score']}** (coverage {meta['coverage_books']}/{meta['coverage_total_books']}, hits {meta['total_hits']}, citations {meta['citation_count']})"
    )
summary.write_text('\n'.join(summary_lines).rstrip() + '\n', encoding='utf-8')

manifest = MEM_TOPICS / 'index.json'
manifest.write_text(json.dumps({'scores': scores}, indent=2), encoding='utf-8')
print('wrote', manifest)
print('wrote', summary)
