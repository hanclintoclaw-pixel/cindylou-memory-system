#!/usr/bin/env python3
"""Inventory unadmitted rules citation aggregates, without reading their targets.

This is mechanical triage, not full-file reviewer attestation, edition verification,
printed-page verification, claim equivalence, source approval or retrieval evidence.
Reference paths remain inert strings. Nothing is imported or changed in production.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from memory_unification_legacy_review import BoundInputs, canonical_root, safe_file, sha, write_new


PREFIX = '10_consolidated/general/entities/'
CITATION = re.compile(r'^- \*\*([^*]+)\*\*(?: p\.([1-9][0-9]*))? — (.*)$')
REFERENCE = re.compile(r'^  - Source: `([^`]+)`$')
COUNT = re.compile(r'^- Reference count: \*\*([0-9]+)\*\*$')


def windows(raw, *, max_chars=6000, max_lines=80):
    """Contiguous non-lossy review plan; refuse a line that exceeds the budget."""
    if type(max_chars) is not int or not 1 <= max_chars <= 16000:
        raise ValueError('invalid character budget')
    if type(max_lines) is not int or not 1 <= max_lines <= 200:
        raise ValueError('invalid line budget')
    lines = raw.decode('utf-8').splitlines()
    result, start = [], 0
    while start < len(lines):
        end, size = start, 0
        while end < len(lines) and end-start < max_lines:
            added = len(lines[end]) + (1 if end > start else 0)
            if size + added > max_chars:
                break
            size += added
            end += 1
        if end == start:
            raise ValueError('single line exceeds bounded review budget')
        result.append({'start_line': start+1, 'end_line': end,
                       'characters': size,
                       'passage_sha256': sha('\n'.join(lines[start:end]).encode('utf-8'))})
        start = end
    return result


def parse_aggregate(raw):
    lines = raw.decode('utf-8').splitlines()
    if not lines or not lines[0].startswith('# Entity: '):
        raise ValueError('entity aggregate heading required')
    citations, unmatched, declared = [], [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = CITATION.fullmatch(line)
        if match:
            ref = REFERENCE.fullmatch(lines[i+1]) if i+1 < len(lines) else None
            if ref is None:
                raise ValueError('citation without adjacent source reference')
            citations.append({'start_line': i+1, 'end_line': i+2,
                              'passage_sha256': sha('\n'.join(lines[i:i+2]).encode('utf-8')),
                              'book_label': match[1],
                              'page_marker': int(match[2]) if match[2] else None,
                              'page_kind': ('unverified-aggregate-label-not-printed-citation'
                                            if match[2] else 'unpaginated-source-not-a-book-citation'),
                              'excerpt_sha256': sha(match[3].encode('utf-8')),
                              'reference_path': ref[1], 'reference_status': 'not-opened'})
            i += 2
            continue
        count = COUNT.fullmatch(line)
        if count:
            declared.append(int(count[1]))
        elif line and not line.startswith(('# Entity: ', '## Cited Mentions', '# ')):
            unmatched.append({'line': i+1, 'sha256': sha(line.encode('utf-8'))})
        i += 1
    if len(declared) > 1 or (declared and declared[0] != len(citations)):
        raise ValueError('declared reference count mismatch')
    return {'entity_label': lines[0][len('# Entity: '):],
            'citations': citations, 'citation_count': len(citations),
            'declared_reference_count': declared[0] if declared else None,
            'unparsed_lines': unmatched}


def inventory(queue_path, source_root):
    root, bound = canonical_root(source_root), BoundInputs()
    queue_path = Path(queue_path)
    if not queue_path.is_absolute() or queue_path.resolve() != queue_path or queue_path.is_symlink():
        raise ValueError('canonical queue required')
    queue_raw = bound.read(queue_path)
    queue = json.loads(queue_raw)
    if queue.get('version') != 1 or queue.get('count') != len(queue.get('sources', [])):
        raise ValueError('invalid queue')
    seen, sources, signatures, books = set(), [], Counter(), Counter()
    for item in queue['sources']:
        name = item['source']
        if name in seen:
            raise ValueError('duplicate queue source')
        seen.add(name)
        if not name.startswith(PREFIX):
            continue
        raw = bound.read(safe_file(root, name))
        if sha(raw) != item['revision'] or len(raw) != item['bytes']:
            raise ValueError('queued aggregate revision/size changed')
        parsed = parse_aggregate(raw)
        for c in parsed['citations']:
            books[c['book_label']] += 1
            signatures[(c['book_label'], c['page_marker'], c['excerpt_sha256'])] += 1
        sources.append({'source': name, 'revision': sha(raw), 'bytes': len(raw),
                        'line_count': len(raw.decode('utf-8').splitlines()),
                        'admission': 'quarantined-unverified',
                        'review_windows': windows(raw), **parsed})
    bound.verify()
    return {'version': 1, 'kind': 'private-rules-derivative-mechanical-triage',
            'created_at': datetime.now(timezone.utc).isoformat(), 'visibility': 'operator',
            'queue_sha256': sha(queue_raw), 'source_root': str(root), 'sources': sources,
            'source_count': len(sources), 'bytes': sum(s['bytes'] for s in sources),
            'citation_rows': sum(s['citation_count'] for s in sources),
            'book_labels': dict(books), 'unparsed_lines': sum(len(s['unparsed_lines']) for s in sources),
            'unpaginated_rows': sum(c['page_marker'] is None for s in sources for c in s['citations']),
            'repeated_identical_label_marker_excerpt_rows': sum(n-1 for n in signatures.values()),
            'content_reviewed_by_this_tool': 0, 'unique_claims': None, 'promoted': 0,
            'limitations': ['Reference paths were not opened; target existence and lineage are unverified.',
                           'SR3 in a filename is not edition verification; p.N is not a printed-page citation.',
                           'Identical label/marker/excerpt rows are duplicate strings, not deduplicated claims.',
                           'Review windows cover lines mechanically; only actual reviewer reads can clear content.',
                           'Quarantine is a candidate disposition, not a production registry or source-rights change.']}


def read_window(queue_path, source_root, source, window):
    # Recompute from source bytes, never trust an editable saved plan's range/hash.
    report = inventory(queue_path, source_root)
    if type(window) is not int or window < 1:
        raise ValueError('positive one-based window required')
    row = next((s for s in report['sources'] if s['source'] == source), None)
    if row is None or window > len(row['review_windows']):
        raise ValueError('unknown source/window')
    raw = safe_file(canonical_root(source_root), source).read_bytes()
    if sha(raw) != row['revision']:
        raise ValueError('source changed before bounded read')
    span = row['review_windows'][window-1]
    text = '\n'.join(raw.decode('utf-8').splitlines()[span['start_line']-1:span['end_line']])
    if sha(text.encode('utf-8')) != span['passage_sha256']:
        raise ValueError('read passage changed')
    return {'source': source, 'revision': row['revision'], 'window': window,
            'window_count': len(row['review_windows']), **span, 'text': text,
            'visibility': 'operator', 'promoted': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--read-source')
    parser.add_argument('--window', type=int)
    args = parser.parse_args()
    if args.read_source is not None:
        if args.window is None or args.output is not None:
            parser.error('bounded read needs --window and no --output')
        print(json.dumps(read_window(args.queue, args.source_root, args.read_source, args.window)))
    else:
        if args.output is None or args.window is not None:
            parser.error('inventory needs --output and no --window')
        report = inventory(args.queue, args.source_root)
        write_new(args.output, report)
        print(json.dumps({k: v for k, v in report.items() if k not in ('sources', 'book_labels')}))


if __name__ == '__main__':
    main()
