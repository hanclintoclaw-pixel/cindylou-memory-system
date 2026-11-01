#!/usr/bin/env python3
"""Private, source-bound legacy review receipts; never import, promote or publish.

Inventory is mechanical triage, NOT semantic review. Review annotations are explicit
reviewer attestations, validated against source bytes and bounded evidence. Exact
copies share byte identity, not independent corroboration or a semantic fact count.
No native reader, database, production configuration or service is touched.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_root(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink() or not path.is_dir():
        raise ValueError('canonical existing root required')
    return path


def safe_file(root, relative):
    if not isinstance(relative, str) or '\\' in relative or '\x00' in relative:
        raise ValueError('invalid relative source')
    parts = relative.split('/')
    if any(not part or part.startswith('.') for part in parts):
        raise ValueError('hidden/traversal/absolute source refused')
    path = root
    for part in parts:
        path /= part
        if path.is_symlink():
            raise ValueError('symlink source refused')
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('source outside root or missing')
    return path


def category(name):
    if '/requests/' in name:
        return 'request'
    if 'INDEX' in name or Path(name).name.startswith('README'):
        return 'index-or-format-notes'
    for suffix, kind in (('.opinion.md', 'opinion'), ('.timeline.md', 'timeline'),
                         ('.description.md', 'description')):
        if name.endswith(suffix):
            return kind
    if '/session_summaries/' in name:
        return 'session-summary'
    if '/sessions/' in name:
        return 'session-note-derivative'
    return 'entity-derivative'


class BoundInputs:
    """Cache exact bytes and reject any observed source drift before publication."""
    def __init__(self):
        self.files = {}

    def read(self, path):
        if path not in self.files:
            before = path.stat()
            raw = path.read_bytes()
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('source changed while reading')
            self.files[path] = raw
        return self.files[path]

    def verify(self):
        for path, raw in self.files.items():
            if path.is_symlink() or path.read_bytes() != raw:
                raise ValueError('source generation changed during review')


def inventory(queue_path, source_root, comparison_roots=()):
    source_root = canonical_root(source_root)
    bound = BoundInputs()
    queue_path = Path(queue_path)
    if queue_path.resolve() != queue_path or queue_path.is_symlink():
        raise ValueError('canonical queue required')
    queue_raw = bound.read(queue_path)
    queue = json.loads(queue_raw)
    if queue.get('version') != 1 or queue.get('count') != len(queue.get('sources', [])):
        raise ValueError('invalid review queue')
    comparisons = {}
    for value in comparison_roots:
        root = canonical_root(value)
        # Explicit comparison roots only; do not walk the full rules corpus.
        for path in sorted(root.rglob('*.md')):
            relative = path.relative_to(root).as_posix()
            if any(p.startswith('.') for p in relative.split('/')):
                continue
            path = safe_file(root, relative)
            raw = bound.read(path)
            comparisons.setdefault(sha(raw), []).append(str(path))
    rows, identities = [], set()
    for row in queue['sources']:
        if row['source'] in identities:
            raise ValueError('duplicate queue source')
        identities.add(row['source'])
        path = safe_file(source_root, row['source'])
        raw = bound.read(path)
        revision = sha(raw)
        if revision != row['revision'] or len(raw) != row['bytes']:
            raise ValueError('queued source revision/size changed')
        rows.append({'review_id': row['review_id'], 'source': row['source'],
                     'revision': revision, 'bytes': len(raw),
                     'category': category(row['source']),
                     'exact_comparison_copies': [p for p in comparisons.get(revision, []) if p != str(path)],
                     'semantic_status': 'unreviewed', 'visibility': 'operator',
                     'promoted': False})
    bound.verify()
    return {'version': 1, 'kind': 'legacy-mechanical-triage',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'queue_sha256': sha(queue_raw), 'source_root': str(source_root),
            'sources': rows, 'count': len(rows),
            'categories': dict(Counter(r['category'] for r in rows)),
            'exact_comparison_copy_count': sum(bool(r['exact_comparison_copies']) for r in rows),
            'semantic_reviewed': 0, 'unique_claims': None, 'promoted': 0,
            'note': 'Mechanical byte/category checks only; exact copies are not independent evidence. No retrieval or semantic equivalence claim.'}


CLASSES = {'operational-metadata', 'research-request-not-scene-evidence',
           'unverified-request-claim', 'historical-source-supported',
           'empty-generated-profile', 'unsupported-generated-inference',
           'cross-entity-contamination', 'unresolved-source-claim', 'stale-or-conflicting-claim'}
RELATIONS = {'supports-historical-passage', 'same-byte-copy', 'research-request-only',
             'different-entity', 'current-record-comparison', 'unresolved', 'contradicts-generated-label'}
LINEAGE = {'no-evidentiary-content', 'request-only', 'historical-passage-verified',
           'mixed-verified-and-unresolved', 'unresolved'}


def validate_review(payload, *, queue_path, source_root, evidence_roots):
    """Validate bindings, not reviewer judgment; no permissions are created here."""
    if (payload.get('version') != 1 or payload.get('kind') != 'private-legacy-semantic-review'
            or payload.get('promoted') != 0 or payload.get('visibility') != 'operator'
            or payload.get('unique_claims') is not None):
        raise ValueError('private nonpromoting review required')
    if not payload.get('reviewer') or payload.get('review_scope') != 'entire-listed-files':
        raise ValueError('explicit reviewer/full-file attestation required')
    bound = BoundInputs()
    queue_raw = bound.read(Path(queue_path))
    if payload.get('queue_sha256') != sha(queue_raw):
        raise ValueError('review queue changed')
    queue = {r['source']: r for r in json.loads(queue_raw)['sources']}
    source_root = canonical_root(source_root)
    roots = {name: canonical_root(root) for name, root in evidence_roots.items()}
    seen = set()

    def passage(raw, start, end):
        lines = raw.decode('utf-8').splitlines()
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError('invalid exact evidence bounds')
        text = '\n'.join(lines[start-1:end])
        if end-start+1 > 200 or len(text) > 16000:
            raise ValueError('evidence exceeds bounded read budget')
        return sha(text.encode('utf-8'))

    records = payload.get('reviews')
    if not isinstance(records, list) or not records:
        raise ValueError('explicit nonempty reviews required')
    for review in records:
        name = review['source']
        if name not in queue or name in seen:
            raise ValueError('unknown/duplicate reviewed source')
        seen.add(name)
        raw = bound.read(safe_file(source_root, name))
        if review.get('revision') != sha(raw) or review['revision'] != queue[name]['revision']:
            raise ValueError('review source revision changed')
        if review.get('review_status') != 'reviewed-not-promoted' or not review.get('findings'):
            raise ValueError('completed nonpromoting findings required')
        if review.get('lineage_status') not in LINEAGE:
            raise ValueError('explicit lineage completeness required')
        for finding in review['findings']:
            if finding.get('classification') not in CLASSES or not finding.get('rationale'):
                raise ValueError('explicit classified reviewer finding required')
            if finding.get('passage_sha256') != passage(raw, finding['start_line'], finding['end_line']):
                raise ValueError('finding passage changed')
            for evidence in finding.get('evidence', []):
                if evidence['root'] not in roots or evidence['relation'] not in RELATIONS:
                    raise ValueError('unknown evidence root/relation')
                other = bound.read(safe_file(roots[evidence['root']], evidence['path']))
                if evidence.get('revision') != sha(other):
                    raise ValueError('lineage evidence revision changed')
                if evidence.get('passage_sha256') != passage(other, evidence['start_line'], evidence['end_line']):
                    raise ValueError('lineage evidence passage changed')
                if evidence['relation'] == 'same-byte-copy' and raw != other:
                    raise ValueError('claimed exact copy differs')
    bound.verify()
    return {'reviewed_files': len(seen), 'remaining_files': len(queue)-len(seen),
            'findings': sum(len(r['findings']) for r in records),
            'lineage_statuses': dict(Counter(r['lineage_status'] for r in records)),
            'classifications': dict(Counter(f['classification'] for r in records for f in r['findings'])),
            'promoted': 0, 'unique_claims': None,
            'note': 'Counts explicit source-bound reviewer attestations, not machine proof of semantic equivalence, retrieval or canon.'}


def write_new(path, payload):
    path = Path(path)
    os.umask(0o077)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(payload, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--comparison-root', action='append', default=[])
    parser.add_argument('--review', type=Path)
    parser.add_argument('--evidence-root', action='append', default=[], help='trusted name=/absolute/root')
    args = parser.parse_args()
    if args.review:
        roots = {}
        for item in args.evidence_root:
            name, sep, root = item.partition('=')
            if not sep or not name or name in roots:
                parser.error('unique evidence name=root required')
            roots[name] = root
        review_raw = args.review.read_bytes()
        payload = json.loads(review_raw)
        result = validate_review(payload, queue_path=args.queue, source_root=args.source_root, evidence_roots=roots)
        if args.review.is_symlink() or args.review.read_bytes() != review_raw:
            raise ValueError('review annotations changed during validation')
        result.update(review_sha256=sha(review_raw), kind='validated-private-review-receipt')
    else:
        result = inventory(args.queue, args.source_root, args.comparison_root)
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}))


if __name__ == '__main__':
    main()
