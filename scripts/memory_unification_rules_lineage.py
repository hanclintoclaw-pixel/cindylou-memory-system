#!/usr/bin/env python3
"""Trace inert aggregate excerpts to explicitly routed OCR pages; never admit rules.

The caller supplies label-to-relative-file routes under one canonical OCR root.
An optional, separately rooted alias must be explicitly supplied and currently
byte-identical to its target. Missing or unequal aliases fail closed; matching
current copies does not establish their historical identity. Embedded references
cannot select files. A page substring match is copy-lineage
evidence only, including for short/ambiguous fragments, not edition, printed-page,
semantic, PDF-image, disclosure, retrieval or current-canon verification.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from memory_unification_legacy_review import BoundInputs, canonical_root, safe_file, sha, write_new
from memory_unification_rules_derivatives import CITATION, PREFIX, parse_aggregate


PAGE = re.compile(r'^===== PAGE ([1-9][0-9]*) =====$')


def page_ranges(raw):
    lines = raw.decode('utf-8').splitlines()
    headings = [(i, int(m[1])) for i, line in enumerate(lines) if (m := PAGE.fullmatch(line))]
    if not headings or len({n for _, n in headings}) != len(headings):
        raise ValueError('missing or duplicate OCR page markers')
    result = {}
    for j, (start, number) in enumerate(headings):
        end = headings[j+1][0] if j+1 < len(headings) else len(lines)
        result[number] = (start+1, end)
    return lines, result


def reconcile_aliases(bound, routed, alias_root, aliases):
    """Verify deliberately selected present aliases, never inferred path repairs."""
    if aliases is None and alias_root is None:
        return {}, {}
    if (not isinstance(aliases, dict) or not aliases or alias_root is None
            or not all(isinstance(k, str) and k in routed for k in aliases)):
        raise ValueError('explicit alias root and nonempty routed-label aliases required')
    root = canonical_root(alias_root)
    selected = {label: safe_file(root, relative) for label, relative in aliases.items()}
    if len(set(selected.values())) != len(selected) or set(selected.values()) & set(routed.values()):
        raise ValueError('overlapping alias targets')
    reports = {}
    for label, path in selected.items():
        target = routed[label]
        alternate, original = bound.read(path), bound.read(target)
        if alternate != original:
            raise ValueError('alternate reference bytes disagree with explicit route')
        reports[label] = {'path': str(path), 'revision': sha(alternate),
                          'target': str(target), 'target_revision': sha(original),
                          'bytes': len(alternate), 'comparison': 'whole-file-byte-identical',
                          'historical_identity_verified': False}
    return selected, reports


def trace(queue_path, source_root, ocr_root, routes, sources, *, alias_root=None, aliases=None):
    root, ocr = canonical_root(source_root), canonical_root(ocr_root)
    if not isinstance(routes, dict) or not routes or not all(isinstance(k, str) and k for k in routes):
        raise ValueError('explicit nonempty label routes required')
    # Validate all supplied routes, not embedded references or basename fallbacks.
    routed = {label: safe_file(ocr, relative) for label, relative in routes.items()}
    if len(set(routed.values())) != len(routed):
        raise ValueError('overlapping route targets')
    if not sources or len(set(sources)) != len(sources):
        raise ValueError('unique explicit source selection required')
    queue_path = Path(queue_path)
    if not queue_path.is_absolute() or queue_path.resolve() != queue_path or queue_path.is_symlink():
        raise ValueError('canonical queue required')
    bound = BoundInputs()
    alias_paths, alias_reports = reconcile_aliases(bound, routed, alias_root, aliases)
    queue_raw = bound.read(queue_path)
    queue = json.loads(queue_raw)
    rows = queue.get('sources', [])
    if queue.get('version') != 1 or queue.get('count') != len(rows) or len({r['source'] for r in rows}) != len(rows):
        raise ValueError('invalid or duplicate review queue')
    queued = {r['source']: r for r in rows}
    result, targets = [], {}
    for name in sources:
        if name not in queued or not name.startswith(PREFIX):
            raise ValueError('unknown aggregate source')
        raw = bound.read(safe_file(root, name))
        if sha(raw) != queued[name]['revision'] or len(raw) != queued[name]['bytes']:
            raise ValueError('queued aggregate revision/size changed')
        lines = raw.decode('utf-8').splitlines()
        for citation in parse_aggregate(raw)['citations']:
            item = {'source': name, 'revision': sha(raw), **citation,
                    'status': 'unmapped-reference', 'original': None,
                    'edition_verified': False, 'printed_page_verified': False}
            label = citation['book_label']
            if label in routed:
                target = routed[label]
                alternate = alias_paths.get(label)
                allowed_references = {str(target)}
                if alternate is not None:
                    allowed_references.add(str(alternate))
                if citation['reference_path'] not in allowed_references:
                    raise ValueError('embedded reference disagrees with explicit route')
                if target not in targets:
                    original = bound.read(target)
                    original_lines, pages = page_ranges(original)
                    targets[target] = (sha(original), original_lines, pages)
                revision, original_lines, pages = targets[target]
                number = citation['page_marker']
                item['reference_status'] = 'explicit-route-opened'
                if citation['reference_path'] != str(target):
                    item['reference_status'] = 'explicit-byte-identical-alias-opened'
                    item['reference_alias'] = alias_reports[label]
                item['original'] = {'path': str(target), 'revision': revision,
                                    'ocr_marker': number}
                if number not in pages:
                    item['status'] = 'ocr-marker-not-found'
                else:
                    start, end = pages[number]
                    excerpt = CITATION.fullmatch(lines[citation['start_line']-1])[3]
                    # No punctuation, spelling, case or whitespace repair. Preserve misses.
                    matches = [i+1 for i in range(start, end)
                               if excerpt and excerpt in original_lines[i]]
                    item['status'] = 'exact-substring-on-ocr-page' if matches else 'excerpt-not-found-on-ocr-page'
                    item['match_count'] = len(matches)
                    item['matches'] = [{'start_line': i, 'end_line': i,
                                        'passage_sha256': sha(original_lines[i-1].encode('utf-8'))}
                                       for i in matches]
                    item['original'].update(page_start_line=start, page_end_line=end,
                        page_sha256=sha('\n'.join(original_lines[start-1:end]).encode('utf-8')))
            result.append(item)
    bound.verify()
    return {'version': 1, 'kind': 'private-aggregate-ocr-copy-lineage',
            'created_at': datetime.now(timezone.utc).isoformat(), 'visibility': 'operator',
            'queue_sha256': sha(queue_raw), 'source_root': str(root), 'ocr_root': str(ocr),
            'routes': routes, 'selected_sources': sources, 'rows': result,
            'alias_root': str(canonical_root(alias_root)) if alias_root is not None else None,
            'verified_aliases': alias_reports,
            'statuses': dict(Counter(r['status'] for r in result)),
            'original_revisions': {str(p): data[0] for p, data in targets.items()},
            'content_reviews_by_tool': 0, 'unique_claims': None, 'promoted': 0,
            'limitations': ['Exact substring location is not a verified claim or independent corroboration.',
                           'OCR page markers are not verified printed-page citations.',
                           'Edition, PDF images, context, fragment ambiguity and semantic scope remain unreviewed.',
                           'Alias equality binds observed current bytes only, not historical path or edition identity.',
                           'Unmapped references stay unopened; misses do not prove source or claim loss.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--ocr-root', type=Path, required=True)
    parser.add_argument('--route', action='append', required=True, help='trusted label=relative/file')
    parser.add_argument('--source', action='append', required=True)
    parser.add_argument('--alias-root', type=Path, help='trusted canonical root for explicit present aliases')
    parser.add_argument('--alias', action='append', help='trusted routed-label=relative/file; byte equality required')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    routes = {}
    for entry in args.route:
        label, separator, relative = entry.partition('=')
        if not separator or not label or label in routes:
            parser.error('unique label=relative/file routes required')
        routes[label] = relative
    aliases = None
    if args.alias:
        aliases = {}
        for entry in args.alias:
            label, separator, relative = entry.partition('=')
            if not separator or not label or label in aliases:
                parser.error('unique routed-label=relative/file aliases required')
            aliases[label] = relative
    report = trace(args.queue, args.source_root, args.ocr_root, routes, args.source,
                   alias_root=args.alias_root, aliases=aliases)
    write_new(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'routes', 'original_revisions')}))


if __name__ == '__main__':
    main()
