#!/usr/bin/env python3
"""Build a reviewed, hash-only fact-exclusion inventory for the U2 shadow harness.

Answers one narrow question with evidence: which facts does legacy retrieval reach
that the public-only partition does not, and are any of them already unreachable
from BOTH backends (orphaned, not lost-by-exclusion)?

Only opaque hashes and counts are written. Fact text is read transiently to test
retrievability against the real legacy reader and is never persisted here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / 'scripts'))

CONTROL = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')
LEGACY_ROOT = Path('/Users/hanclaw/claw/projects/cindylou/memory-system')
WIKI_PAGE = Path('/Users/hanclaw/claw/projects/cindylou/campaign-wiki/NPCs/Tom-Erlichman.md')
CHAT_FACTS = Path('/Volumes/carbonite/claw/data/cindylou/cleaned/memory/99_runtime/chat_facts.jsonl')
DOC_ID = 'wiki/NPCs/Tom-Erlichman.md'
OUTPUT = CONTROL/'shadow-fact-review.private.json'
MIN_UNITS = 3


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def units_from(text: str, start: int, end: int):
    """Contentful lines in an inclusive source range, 1-based."""
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if not (start <= number <= end):
            continue
        stripped = re.sub(r'^[\s\-\*\#]+', '', line).strip()
        if len(stripped) >= 12:  # skip headings-only/blank noise, keep real assertions
            out.append({'line': number, 'text': stripped})
    return out


def distinctive(text: str) -> str:
    """Pick the rarest-looking token as a probe; legacy scoring is term-based."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]{4,}", text)]
    if not words:
        words = re.findall(r'\d+', text)
    if not words:
        return text[:24]
    # Proper nouns carry the ranking in this corpus (see keyword_search's stem boost).
    proper = [w for w in words if w[0].isupper()]
    return (proper or words)[0]


def main():
    sys.path.insert(0, str(LEGACY_ROOT))
    import importlib.util
    spec = importlib.util.spec_from_file_location('fact_review_bridge',
                                                  LEGACY_ROOT/'05_serving/memory_bridge.py')
    bridge = importlib.util.module_from_spec(spec)
    sys.modules['fact_review_bridge'] = bridge
    spec.loader.exec_module(bridge)

    # Reachable doc set for the campaign scope legacy actually walks.
    walk = [str(p.resolve()) for p in bridge._iter_docs('campaign')]
    walk_set = set(walk)
    page_reachable = str(WIKI_PAGE.resolve()) in walk_set
    page_text = WIKI_PAGE.read_text()
    # Match on the authoritative doc_id the reader itself assigns, never on filename guessing.
    page_doc_id = bridge._doc_id(WIKI_PAGE)
    jsonl_in_walk = any(p.endswith('.jsonl') for p in walk_set)

    def legacy_reaches(probe: str, want_doc_id: str, scope: str) -> bool:
        if not probe:
            return False
        hits = bridge.keyword_search(query=probe, scope=scope, limit=8)
        return any(h.doc_id == want_doc_id for h in hits)

    records = []
    orphaned = []
    manifest = json.loads((CONTROL/'native-public-pilot-20261031c/partition.json').read_text())
    in_partition = {r['evidence']['doc_id'] for r in manifest['records']}
    group_sha = sha(DOC_ID)

    sections = [('known', 19, 33, 'public'), ('background-draft', 35, 45, 'gm'),
                ('build-draft', 47, 157, 'gm')]
    for section_id, start, end, visibility in sections:
        units = units_from(page_text, start, end)
        if len(units) < MIN_UNITS:
            raise ValueError(f'section {section_id} produced too few fact units')
        for unit in units:
            probe = distinctive(unit['text'])
            retrievable = page_reachable and legacy_reaches(probe, page_doc_id, 'campaign')
            record = {'fact_sha256': sha(f'{DOC_ID}#{section_id}:{unit["line"]}'),
                      'evidence_group_sha256': group_sha,
                      'public': visibility == 'public',
                      'legacy_retrievable': bool(retrievable),
                      'unified_retrievable': f'{DOC_ID}#{section_id}' in in_partition}
            records.append(record)
            if not record['public'] and not record['legacy_retrievable']:
                orphaned.append({'kind': 'wiki-section', 'section': section_id,
                                 'fact_sha256': record['fact_sha256']})

    # Chat facts: legacy's own index. Unknown visibility is treated as private.
    chat_rows = []
    if CHAT_FACTS.is_file():
        for line in CHAT_FACTS.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            fact_text = str(payload.get('fact') or payload.get('text') or '')
            visibility = str(payload.get('visibility', '')).lower()
            probe = distinctive(fact_text)
            # keyword_search only walks *.md roots, so a .jsonl row cannot be returned as a
            # hit; 'direct' therefore tests that fact rather than assuming it.
            direct = jsonl_in_walk and legacy_reaches(probe, bridge._doc_id(CHAT_FACTS), 'all')
            record = {'fact_sha256': sha(line), 'evidence_group_sha256': sha('chat_facts.jsonl'),
                      'public': visibility == 'public', 'legacy_retrievable': bool(direct),
                      'unified_retrievable': False}
            records.append(record)
            chat_rows.append(record)

    if not records:
        raise ValueError('no fact units reviewed; refusing to emit an inventory')
    payload = {
        'reviewer': 'cindylou-local-review',
        'method': ('Fact units are per-line content of reviewed registry sections plus every '
                   'chat_facts.jsonl row. legacy_retrievable was tested by calling the real '
                   'memory_bridge.keyword_search with a distinctive probe and requiring the '
                   'owning document back; a fact is never marked reachable by assertion. '
                   'unified_retrievable requires the fact section to be in the validated '
                   'public partition manifest. Unknown chat visibility is treated as private.'),
        'generated_note': 'Hashes only. No fact text, snippets, or copyrighted corpus text.',
        'corpus': {'page_sha256': sha(page_text),
                   'chat_facts_sha256': sha(CHAT_FACTS.read_text()) if CHAT_FACTS.is_file() else None,
                   'page_in_legacy_campaign_walk': page_reachable,
                   'chat_facts_in_legacy_walk': jsonl_in_walk,
                   'partition_manifest_sha256': sha((CONTROL/'native-public-pilot-20261031c/partition.json').read_text())},
        'summary': {'wiki_units': sum(1 for r in records if r['evidence_group_sha256'] == group_sha),
                    'wiki_units_legacy_reachable': sum(1 for r in records
                                                       if r['evidence_group_sha256'] == group_sha
                                                       and r['legacy_retrievable']),
                    'chat_rows': len(chat_rows),
                    'chat_directly_legacy_reachable': sum(1 for r in chat_rows if r['legacy_retrievable'])},
        'records': records,
    }
    fd = None
    try:
        fd = __import__('os').open(OUTPUT, __import__('os').O_WRONLY | __import__('os').O_CREAT |
                                   __import__('os').O_TRUNC, 0o600)
        with __import__('os').fdopen(fd, 'w') as stream:
            json.dump(payload, stream, indent=2)
            stream.write('\n')
    except Exception:
        if fd is not None:
            __import__('os').close(fd)
        raise
    print(json.dumps({'output': str(OUTPUT), 'records': len(records),
                      'orphaned_nonpublic_not_legacy_reachable': len(orphaned),
                      'chat_facts_in_legacy_walk': jsonl_in_walk,
                      'wiki_units_legacy_reachable': payload['summary']['wiki_units_legacy_reachable'],
                      'chat_directly_legacy_reachable': payload['summary']['chat_directly_legacy_reachable'],
                      'page_in_legacy_campaign_walk': page_reachable,
                      'page_doc_id': page_doc_id}, indent=2))


if __name__ == '__main__':
    main()
