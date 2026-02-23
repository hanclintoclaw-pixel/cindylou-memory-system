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
HARM = P.outputs_root / 'harmonized_all'
WP = P.memory_root / 'wordpress_ingest'
OUT = P.memory_root / 'lore'
ENT_DIR = OUT / 'entities'
OUT.mkdir(parents=True, exist_ok=True)
ENT_DIR.mkdir(parents=True, exist_ok=True)

PAGE_RE = re.compile(r'^=====\s*PAGE\s+(\d+)\s*=====\s*$', re.MULTILINE)

ENTITY_PATTERNS = {
    # megacorps / factions
    'Renraku': r'\brenraku\b', 'Ares': r'\bares\b', 'Aztechnology': r'\baztechnology\b',
    'Saeder-Krupp': r'\bsaeder\s*[- ]?krupp\b', 'Fuchi': r'\bfuchi\b',
    'Shiawase': r'\bshiawase\b', 'Mitsuhama': r'\bmitsuhama\b',
    # matrix / ai / host
    'Matrix': r'\bmatrix\b', 'Host': r'\bhost\b', 'ICE': r'\bice\b|\bintrusion countermeasures\b',
    'IC': r'\bic\b', 'Deus': r'\bdeus\b', 'Megaera': r'\bmegaera\b', 'Mirage': r'\bmirage\b',
    'Deck': r'\bdeck\w*\b', 'Persona': r'\bpersona\b', 'MPCP': r'\bmpcp\b',
    'Sleaze': r'\bsleaze\b', 'Masking': r'\bmasking\b', 'Browse': r'\bbrowse\b', 'Analyze': r'\banalyze\b',
    'Deception': r'\bdeception\b', 'Read/Write': r'\bread\/?write\b', 'Attack': r'\battack\b',
    'Armor': r'\barmor\b', 'Restore': r'\brestore\b',
    # races / critters / magic
    'Elf': r'\belf\b|\belves\b', 'Dwarf': r'\bdwarf\b|\bdwarves\b', 'Ork': r'\bork\b|\borks\b',
    'Troll': r'\btroll\b|\btrolls\b', 'Human': r'\bhuman\b|\bhumans\b',
    'Dragon': r'\bdragon\w*\b', 'Sasquatch': r'\bsasquatch\b', 'Unicorn': r'\bunicorn\b',
    'Spell': r'\bspell\w*\b', 'Conjuring': r'\bconjur\w*\b', 'Adept': r'\badept\b',
    # rigging / equipment
    'Rigger': r'\brigger\b|\brigging\b|\bvcr\b', 'Drone': r'\bdrones?\b', 'Vehicle': r'\bvehicle\b',
    # gangs / politics examples
    'Humanis': r'\bhumanis\b',
}


def parse_pages(text: str):
    ms = list(PAGE_RE.finditer(text))
    pages = {}
    for i, m in enumerate(ms):
        p = int(m.group(1))
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        pages[p] = text[start:end].strip()
    return pages


def pick_line(text: str, pat: str):
    rx = re.compile(pat, re.IGNORECASE)
    for ln in text.splitlines():
        s = ln.strip()
        if s and rx.search(s):
            return s[:260]
    return ''


entity_index = {k: [] for k in ENTITY_PATTERNS}

# SR3 corpus (page-cited)
for book_dir in sorted([p for p in HARM.glob('*') if p.is_dir()]):
    hfile = book_dir / 'harmonized.md'
    if not hfile.exists():
        continue
    pages = parse_pages(hfile.read_text(encoding='utf-8', errors='replace'))
    for page_no, page_text in pages.items():
        lower = page_text.lower()
        for name, pat in ENTITY_PATTERNS.items():
            if re.search(pat, lower, flags=re.IGNORECASE):
                entity_index[name].append({
                    'source_kind': 'manual',
                    'manual': book_dir.name,
                    'page': page_no,
                    'source': str(hfile),
                    'snippet': pick_line(page_text, pat) or page_text[:220],
                })

# Imported wordpress content as general lore source (except Run Notes)
for folder in ['Homebrew', 'Locations', 'NPCs']:
    root = WP / folder
    if not root.exists():
        continue
    for md in sorted(root.glob('*.md')):
        txt = md.read_text(encoding='utf-8', errors='replace')
        lower = txt.lower()
        for name, pat in ENTITY_PATTERNS.items():
            if re.search(pat, lower, flags=re.IGNORECASE):
                entity_index[name].append({
                    'source_kind': 'wordpress',
                    'manual': f'Wordpress/{folder}',
                    'page': None,
                    'source': str(md),
                    'snippet': pick_line(txt, pat) or txt[:220],
                })

for name, refs in entity_index.items():
    p = ENT_DIR / f"{name.lower().replace('/', '_')}.md"
    lines = [f'# Entity: {name}', '', f'- Reference count: **{len(refs)}**', '', '## Cited Mentions', '']
    if not refs:
        lines.append('_No cited mentions yet._')
    for r in refs:
        if r['page'] is not None:
            lines.append(f"- **{r['manual']}** p.{r['page']} — {r['snippet']}")
        else:
            lines.append(f"- **{r['manual']}** — {r['snippet']}")
        lines.append(f"  - Source: `{r['source']}`")
    p.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

gloss = OUT / 'GLOSSARY.md'
lines = [
    '# SR3 General Knowledge Glossary (Cited)',
    '',
    'Includes rulebook-derived citations plus imported historical wordpress context where available.',
    '',
]
for name, refs in sorted(entity_index.items(), key=lambda kv: len(kv[1]), reverse=True):
    slug = name.lower().replace('/', '_')
    lines.append(f"- **{name}** — {len(refs)} refs (`entities/{slug}.md`)")
gloss.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

idx = OUT / 'index.json'
idx.write_text(json.dumps({k: len(v) for k, v in entity_index.items()}, indent=2), encoding='utf-8')
print('wrote', idx)
print('wrote', gloss)
