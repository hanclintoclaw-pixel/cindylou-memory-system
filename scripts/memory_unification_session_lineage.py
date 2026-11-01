#!/usr/bin/env python3
"""Mechanical, private passage-copy checks; never semantic review or source approval."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

try:
    from .memory_unification_legacy_review import BoundInputs, canonical_root, safe_file, sha, write_new
except ImportError:
    from memory_unification_legacy_review import BoundInputs, canonical_root, safe_file, sha, write_new


CHUNK = re.compile(r'^### Chunk (\d+) — ([^/\\]+\.md) \(L(\d+)-L(\d+)\)$')
DATE = re.compile(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)')


def ranges(raw, start, end):
    """Split exact passage coordinates to the review validator's read budget."""
    lines = raw.decode('utf-8').splitlines()
    if not 1 <= start <= end <= len(lines):
        raise ValueError('invalid passage coordinates')
    result, first, size = [], start, 0
    for i in range(start, end+1):
        width = len(lines[i-1]) + (i != first)
        if len(lines[i-1]) > 16000:
            raise ValueError('single line exceeds bounded passage budget')
        if i-first >= 200 or size+width > 16000:
            result.append(binding(raw, first, i-1))
            first, size, width = i, 0, len(lines[i-1])
        size += width
    result.append(binding(raw, first, end))
    return result


def binding(raw, start, end):
    return {'start_line': start, 'end_line': end,
            'passage_sha256': sha('\n'.join(raw.decode('utf-8').splitlines()[start-1:end]).encode())}


def compare_session(name, *, source_root, original_roots, original_prefixes, bound):
    raw = bound.read(safe_file(source_root, name))
    lines = raw.decode('utf-8').splitlines()
    if not lines or lines[0] != '# Campaign Session: '+Path(name).stem:
        raise ValueError('unrecognized session wrapper')
    chunks = [(i, CHUNK.fullmatch(line)) for i, line in enumerate(lines) if CHUNK.fullmatch(line)]
    if not chunks or len(chunks) != len(set(m.group(2) for _, m in chunks)):
        raise ValueError('missing or duplicate source chunks')
    if f'- Source chunks: **{len(chunks)}**' not in lines[:6]:
        raise ValueError('source chunk count mismatch')
    output = []
    for k, (offset, match) in enumerate(chunks):
        number, original_name, start, end = match.groups()
        if int(number) != k+1:
            raise ValueError('nonsequential source chunks')
        limit = chunks[k+1][0] if k+1 < len(chunks) else len(lines)
        trailers = [i for i in range(offset+1, limit) if lines[i] == f'Source: `{original_name}`']
        if len(trailers) != 1 or any(l.strip() for l in lines[trailers[0]+1:limit]):
            raise ValueError('missing, duplicate or nonterminal source trailer')
        first, last = offset+1, trailers[0]-1
        while first <= last and not lines[first].strip(): first += 1
        while last >= first and not lines[last].strip(): last -= 1
        if first > last:
            raise ValueError('empty source chunk')
        candidates = [(key, root) for key, root in original_roots.items()
                      if original_name.startswith(original_prefixes[key])]
        if len(candidates) != 1:
            raise ValueError('missing or ambiguous original; no basename fallback')
        root_key, root = candidates[0]
        original = bound.read(safe_file(root, original_name))
        original_lines = original.decode('utf-8').splitlines()
        start, end = int(start), int(end)
        original_ranges = ranges(original, start, end)
        body = '\n'.join(lines[first:last+1])
        original_body = '\n'.join(original_lines[start-1:end])
        normalized = ' '.join(body.split())
        # Only dated level-1/2 headings delimit a session, not subordinate Today/recap headings.
        dated = [(i+1, line, DATE.search(line).group()) for i, line in enumerate(original_lines)
                 if re.match(r'^#{1,2} ', line) and DATE.search(line)]
        preceding = [x for x in dated if x[0] <= start]
        heading = preceding[-1] if preceding else None
        crossing = any(start < i <= end for i, _, _ in dated)
        chronology = 'unverified-no-dated-heading'
        if heading:
            chronology = ('crosses-dated-section' if crossing else
                          'matching-enclosing-heading' if heading[2] == Path(name).stem else
                          'conflicting-enclosing-heading')
            if heading[1].startswith('# Imported Scanned Note:') and not crossing:
                chronology = ('matching-imported-wrapper-only' if heading[2] == Path(name).stem else
                              'conflicting-imported-wrapper-only')
        output.append({'chunk': k+1, 'source_body': ranges(raw, first+1, last+1),
                       'original': {'root': root_key, 'path': original_name, 'revision': sha(original),
                                    'passages': original_ranges},
                       'exact_passage_equal': body == original_body,
                       'whitespace_only_equal': normalized == ' '.join(original_body.split()),
                       'normalized_body_sha256': sha(normalized.encode()),
                       'chronology': chronology,
                       'enclosing_heading': ({'text': heading[1], **binding(original, heading[0], heading[0])}
                                             if heading else None)})
    return {'source': name, 'revision': sha(raw), 'chunks': output}


def run(queue_path, source_root, original_roots, original_prefixes):
    source_root = canonical_root(source_root)
    roots = {name: canonical_root(value) for name, value in original_roots.items()}
    if set(roots) != set(original_prefixes) or any(not value for value in original_prefixes.values()):
        raise ValueError('explicit nonempty original prefix for each root required')
    bound = BoundInputs()
    queue_raw = bound.read(Path(queue_path))
    queue = json.loads(queue_raw)
    if queue.get('version') != 1 or queue.get('count') != len(queue.get('sources', [])):
        raise ValueError('invalid queue')
    results, seen = [], set()
    for row in queue['sources']:
        if row['source'] in seen:
            raise ValueError('duplicate queue source')
        seen.add(row['source'])
        if '/sessions/' not in row['source'] or Path(row['source']).name == 'SESSION_INDEX.md':
            continue
        result = compare_session(row['source'], source_root=source_root, original_roots=roots,
                                 original_prefixes=original_prefixes, bound=bound)
        if result['revision'] != row['revision']:
            raise ValueError('queued source revision changed')
        results.append(result)
    bound.verify()
    return {'version': 1, 'kind': 'private-mechanical-session-passage-comparison',
            'created_at': datetime.now(timezone.utc).isoformat(), 'visibility': 'operator',
            'queue_sha256': sha(queue_raw), 'source_root': str(source_root),
            'original_roots': {key: str(value) for key, value in roots.items()},
            'original_prefixes': original_prefixes,
            'comparisons': results, 'source_count': len(results),
            'chunk_count': sum(len(r['chunks']) for r in results),
            'all_passages_whitespace_equal': all(c['whitespace_only_equal'] for r in results for c in r['chunks']),
            'content_reviewed_by_this_tool': 0, 'promoted': 0, 'unique_claims': None,
            'limitations': 'Mechanical copied-passage and heading checks only. OCR extraction is not PDF verification; an inferred date is not an event date. No independent corroboration, canon, retrieval, disclosure or semantic equivalence conclusion.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--queue', required=True, type=Path)
    ap.add_argument('--source-root', required=True, type=Path)
    ap.add_argument('--original-root', required=True, action='append', help='name=/canonical/root')
    ap.add_argument('--original-prefix', required=True, action='append', help='root-name=filename-prefix')
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    roots = {}
    for value in args.original_root:
        name, sep, path = value.partition('=')
        if not sep or not name or name in roots: ap.error('unique name=root required')
        roots[name] = path
    prefixes = {}
    for value in args.original_prefix:
        name, sep, prefix = value.partition('=')
        if not sep or not name or name in prefixes: ap.error('unique name=prefix required')
        prefixes[name] = prefix
    result = run(args.queue, args.source_root, roots, prefixes)
    write_new(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key not in {'comparisons', 'original_roots'}}))


if __name__ == '__main__':
    main()
