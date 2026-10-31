#!/usr/bin/env python3
"""Revision-bound reviewed claims, separate from descriptive source-line probes.

A line, heading, table row, keyword hit or partition membership is NOT a semantic
fact. This command creates a NEW descriptive inventory with zero reviewed claims;
reviewed claims/receipts may subsequently be supplied in another new private file.
No source approval, production reader, native CLI or service is invoked here.

v2 claims have an explicitly reviewed canonical proposition SHA256 (shared by
copies/derivatives), source revision/range/passage SHA256 lineage, and per-backend
query + bounded-get receipts. A successful candidate search is not fact support:
only an exact source-bound read with a separate supporting-passage review is.
Search misses remain ranking misses/unknown; successful direct get disproves
source unreachability. Exclusion is scoped to reviewed lineage, never a claim of
global semantic absence. Unique loss is unassessed unless equivalence review is
explicitly complete and every canonical claim has conclusive paired receipts.

Private inventories contain identifiers/hashes/counts only, not proposition,
query or passage text. Source revisions hash exact original bytes. Passage/read
hashes serialize exactly like MemoryService/native bounded get: UTF-8 encoding
of "\\n".join(source_text.splitlines()[start_line-1:end_line]), with no trailing
newline. Candidate list order is rank; explicit rank fields are not accepted.
Review labels/completeness are trusted reviewer attestations, not independently
verified whole-corpus semantic equivalence. Historical v1 receipts are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

WORKTREE = Path(__file__).resolve().parents[1]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))

from unification.native_client import validate_generation
from unification.policy import StaleReference

SHA256 = re.compile(r'[0-9a-f]{64}\Z')
STATUSES = {'ok', 'empty', 'denied', 'stale', 'unavailable'}
KIND = 'reviewed-claim-evidence-v2'


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        raise ValueError('invalid reviewed claim inventory fields')


def _hash(value):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError('exact SHA256 required')
    return value


def _review(value, *, semantic=False):
    required = {'reviewer', 'rubric_sha256'} | ({'unit_kind'} if semantic else set())
    _fields(value, required)
    if not isinstance(value['reviewer'], str) or not value['reviewer'].strip():
        raise ValueError('explicit completed reviewer required')
    _hash(value['rubric_sha256'])
    if semantic and value['unit_kind'] != 'semantic-claim':
        raise ValueError('headings/rows/probes are not reviewed semantic claims')


def _source_path(registry, doc_id):
    if not isinstance(doc_id, str) or '#' in doc_id or '\\' in doc_id or '\x00' in doc_id:
        raise ValueError('canonical source document ID required')
    parts = doc_id.split('/')
    if len(parts) < 2 or any(not p or p.startswith('.') for p in parts):
        raise ValueError('invalid source identity')
    source = registry.sources.get(parts[0])
    if source is None:
        raise ValueError('source namespace not in supplied registry')
    path = source.root
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('noncanonical source root')
    for part in parts[1:]:
        path /= part
        if path.is_symlink():
            raise ValueError('symlink source not accepted')
    if not path.resolve().is_relative_to(source.root):
        raise ValueError('source outside supplied registry root')
    return path


def _range(value, lines, *, bounded=False):
    start, end = value['start_line'], value['end_line']
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ValueError('invalid source bounds')
    if bounded and end - start + 1 > 200:
        raise ValueError('bounded get must not exceed 200 lines')
    # Match MemoryService.get / native bounded text, not original newline bytes.
    passage = '\n'.join(''.join(lines).splitlines()[start-1:end])
    if bounded and len(passage) > 16000:
        raise ValueError('reviewed passage exceeds bounded-get character limit')
    return passage


def describe_source(text):
    """Descriptive units only: never call any count below facts/reachability."""
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        kind = ('heading' if re.match(r'^#{1,6}\s', stripped) else
                'table-row' if stripped.startswith('|') else 'other-content-line')
        rows.append({'line': number, 'kind': kind, 'line_sha256': sha(line)})
    return {'nonempty_lines': len(rows),
            'headings': sum(row['kind'] == 'heading' for row in rows),
            'table_rows': sum(row['kind'] == 'table-row' for row in rows),
            'units': rows, 'semantic_claim_count': None,
            'note': 'Source-line descriptors only; no proposition or reachability inference.'}


def _generation(registry_path, partition, source_ids):
    registry_path, partition = Path(registry_path), Path(partition)
    registry_raw = registry_path.read_bytes()
    manifest_raw = (partition/'partition.json').read_bytes()
    manifest = json.loads(manifest_raw)
    registry = validate_generation(registry_path, partition, manifest)
    sources = {}
    for doc_id in sorted(source_ids):
        raw = _source_path(registry, doc_id).read_bytes()
        sources[doc_id] = {'revision': sha(raw), 'lines': raw.decode('utf-8').splitlines(keepends=True)}
    generation = {'registry_sha256': sha(registry_raw), 'partition_manifest_sha256': sha(manifest_raw),
                  'sources': [{'doc_id': doc_id, 'revision': row['revision']} for doc_id, row in sources.items()]}
    # Validate again after source I/O; never certify mismatched generations.
    validate_generation(registry_path, partition, manifest)
    if registry_path.read_bytes() != registry_raw or (partition/'partition.json').read_bytes() != manifest_raw:
        raise StaleReference('inventory generation changed during validation')
    for doc_id, row in sources.items():
        if sha(_source_path(registry, doc_id).read_bytes()) != row['revision']:
            raise StaleReference('inventory source changed during validation')
    return generation, registry, manifest, sources


def build_inventory(*, registry_path, partition, source_ids=None):
    """Build an unreviewed v2 descriptive artifact. Never auto-promote source lines."""
    if source_ids is None:
        raw = json.loads(Path(registry_path).read_bytes())
        source_ids = [s['namespace']+'/'+a['path'] for s in raw['sources'] for a in s['approvals']]
    generation, _, _, sources = _generation(registry_path, partition, set(source_ids))
    return {'version': 2, 'kind': KIND, 'generation': generation,
            'review_scope': None, 'claims': [],
            'descriptive_probe_inventory': [
                {'doc_id': doc_id, 'revision': row['revision'], **describe_source(''.join(row['lines']))}
                for doc_id, row in sources.items()]}


class _ValidatedInventory(dict):
    """An in-process receipt tied to trusted explicit generation arguments."""
    def __init__(self, payload, registry_path, partition):
        super().__init__(payload)
        self.registry_path, self.partition = Path(registry_path), Path(partition)


def _validate(payload, *, registry_path, partition):
    _fields(payload, {'version', 'kind', 'generation', 'review_scope', 'claims', 'descriptive_probe_inventory'})
    if payload['version'] != 2 or payload['kind'] != KIND:
        raise ValueError('v2 reviewed-claim inventory required; historical line inventories are not fact evidence')
    binding = payload['generation']
    _fields(binding, {'registry_sha256', 'partition_manifest_sha256', 'sources'})
    _hash(binding['registry_sha256']); _hash(binding['partition_manifest_sha256'])
    if not isinstance(binding['sources'], list):
        raise ValueError('explicit source revisions required')
    source_ids = []
    for source in binding['sources']:
        _fields(source, {'doc_id', 'revision'})
        _hash(source['revision'])
        source_ids.append(source['doc_id'])
    if len(set(source_ids)) != len(source_ids):
        raise ValueError('duplicate generation source')
    current, _, manifest, sources = _generation(registry_path, partition, source_ids)
    if current != binding:
        raise StaleReference('reviewed inventory source/registry/partition generation is stale')
    scope = payload['review_scope']
    if scope is not None:
        _fields(scope, {'reviewer', 'rubric_sha256', 'scope_sha256', 'equivalent_evidence_complete'})
        _review({k: scope[k] for k in ('reviewer', 'rubric_sha256')})
        _hash(scope['scope_sha256'])
        if type(scope['equivalent_evidence_complete']) is not bool:
            raise ValueError('explicit equivalence-review completeness required')
    if not isinstance(payload['claims'], list) or not isinstance(payload['descriptive_probe_inventory'], list):
        raise ValueError('claims and descriptive inventory must be lists')
    # Descriptors are also validated, not a covert arbitrary text field.
    for descriptor in payload['descriptive_probe_inventory']:
        doc_id = descriptor.get('doc_id')
        if doc_id not in sources:
            raise ValueError('descriptor not in bound source generation')
        expected = {'doc_id': doc_id, 'revision': sources[doc_id]['revision'],
                    **describe_source(''.join(sources[doc_id]['lines']))}
        if descriptor != expected:
            raise ValueError('source descriptors do not match exact source revision')
    for claim in payload['claims']:
        _fields(claim, {'claim_sha256', 'canonical_query_sha256', 'review', 'lineage', 'receipts'})
        _hash(claim['claim_sha256']); _hash(claim['canonical_query_sha256']); _review(claim['review'], semantic=True)
        if not isinstance(claim['lineage'], list) or not claim['lineage']:
            raise ValueError('explicit derivative-aware source lineage required')
        lineage = []
        for evidence in claim['lineage']:
            _fields(evidence, {'doc_id', 'revision', 'start_line', 'end_line', 'passage_sha256', 'origin_sha256'})
            doc_id = evidence['doc_id']
            if doc_id not in sources or evidence['revision'] != sources[doc_id]['revision']:
                raise StaleReference('claim lineage source revision changed')
            _hash(evidence['origin_sha256']); _hash(evidence['passage_sha256'])
            passage = _range(evidence, sources[doc_id]['lines'], bounded=True)
            if evidence['passage_sha256'] != sha(passage):
                raise StaleReference('reviewed claim passage differs from authoritative source')
            lineage.append(evidence)
        if not isinstance(claim['receipts'], dict) or set(claim['receipts']) != {'legacy', 'unified'}:
            raise ValueError('paired legacy/unified receipt lists required')
        for backend, receipts in claim['receipts'].items():
            if not isinstance(receipts, list):
                raise ValueError('receipt list required')
            for receipt in receipts:
                _fields(receipt, {'query'}, {'get', 'support_review'})
                query = receipt['query']
                _fields(query, {'query_sha256', 'status', 'candidates'})
                _hash(query['query_sha256'])
                if query['query_sha256'] != claim['canonical_query_sha256']:
                    raise ValueError('paired receipts must use the reviewed canonical query')
                if query['status'] not in STATUSES or not isinstance(query['candidates'], list):
                    raise ValueError('explicit query status/candidates required')
                if (query['status'] == 'ok') != bool(query['candidates']):
                    raise ValueError('query status must match admitted candidate presence')
                identities = set()
                for candidate in query['candidates']:
                    _fields(candidate, {'doc_id', 'revision'})
                    if not isinstance(candidate['doc_id'], str) or not candidate['doc_id']:
                        raise ValueError('candidate document identity required')
                    _hash(candidate['revision'])
                    identity = (candidate['doc_id'], candidate['revision'])
                    if identity in identities:
                        raise ValueError('duplicate candidate identities distort implicit ranks')
                    identities.add(identity)
                    file_id = candidate['doc_id'].split('#')[0]
                    if file_id in sources and candidate['revision'] != sources[file_id]['revision']:
                        raise StaleReference('candidate revision differs from bound source generation')
                got = receipt.get('get')
                if got is None:
                    if 'support_review' in receipt:
                        raise ValueError('candidate-only receipt cannot support a claim')
                    continue
                _fields(got, {'status', 'doc_id', 'revision', 'start_line', 'end_line'}, {'content_sha256'})
                if got['status'] not in STATUSES:
                    raise ValueError('explicit bounded-read status required')
                if not isinstance(got['doc_id'], str) or not got['doc_id']:
                    raise ValueError('bounded get source identity required')
                _hash(got['revision'])
                if type(got['start_line']) is not int or type(got['end_line']) is not int:
                    raise ValueError('exact integer bounded-get coordinates required')
                file_id = got['doc_id'].split('#')[0]
                match = next((e for e in lineage if e['doc_id'] == file_id and
                              e['revision'] == got['revision'] and e['start_line'] == got['start_line'] and
                              e['end_line'] == got['end_line']), None)
                if match is None:
                    raise ValueError('bounded get is not bound to reviewed claim lineage')
                if got['status'] == 'ok':
                    if got.get('content_sha256') != match['passage_sha256']:
                        raise ValueError('bounded get does not match authoritative reviewed passage')
                    if backend == 'unified' and not any(
                            record['evidence']['doc_id'] == got['doc_id'] and
                            record['evidence']['revision'] == got['revision'] and
                            record['evidence']['source_start_line'] <= got['start_line'] <=
                            got['end_line'] <= record['evidence']['source_end_line']
                            for record in manifest['records']):
                        raise ValueError('unified successful get outside reviewed public partition')
                elif 'content_sha256' in got:
                    raise ValueError('non-ok get must not supply content')
                if 'support_review' in receipt:
                    review = receipt['support_review']
                    _fields(review, {'reviewer', 'rubric_sha256', 'status'})
                    _review({k: review[k] for k in ('reviewer', 'rubric_sha256')})
                    if got['status'] != 'ok' or review['status'] not in {'supports', 'does_not_support'}:
                        raise ValueError('support review requires actual successful bounded evidence')
    return manifest


def _eligible(evidence, manifest):
    return any(record['evidence']['doc_id'].split('#')[0] == evidence['doc_id'] and
               record['evidence']['revision'] == evidence['revision'] and
               record['evidence']['source_start_line'] <= evidence['start_line'] <=
               evidence['end_line'] <= record['evidence']['source_end_line']
               for record in manifest['records'])


def load_fact_inventory(path, *, registry_path, partition):
    """Reject stale/v1 inventories; authority comes only from explicit supplied paths."""
    payload = json.loads(Path(path).read_bytes())
    _validate(payload, registry_path=registry_path, partition=partition)
    return _ValidatedInventory(payload, registry_path, partition)


def _receipt_support(receipt):
    return (receipt.get('get', {}).get('status') == 'ok' and
            receipt.get('support_review', {}).get('status') == 'supports')


def summarize_claims(payload):
    """Summarize validated canonical claims; unknown is never coerced to false."""
    if not isinstance(payload, _ValidatedInventory):
        raise ValueError('load and validate inventory against explicit generation before summarizing')
    manifest = _validate(payload, registry_path=payload.registry_path, partition=payload.partition)
    groups = {}
    for row in payload['claims']:
        groups.setdefault(row['claim_sha256'], []).append(row)
    lost, outcomes = [], []
    all_conclusive = bool(groups)
    for claim_id, rows in sorted(groups.items()):
        lineage = {json.dumps(e, sort_keys=True): e for r in rows for e in r['lineage']}.values()
        paired = {backend: [r for row in rows for r in row['receipts'][backend]]
                  for backend in ('legacy', 'unified')}
        states = {}
        for backend, receipts in paired.items():
            support = [r for r in receipts if _receipt_support(r)]
            if support:
                states[backend] = ('query_and_read_support' if any(
                    any(c['doc_id'] == r['get']['doc_id'] and c['revision'] == r['get']['revision']
                        for c in r['query']['candidates']) for r in support) else 'direct_read_support')
            elif backend == 'unified' and all(not _eligible(e, manifest) and any(
                    r.get('get', {}).get('status') == 'denied' and
                    r['get']['doc_id'].split('#')[0] == e['doc_id'] and
                    r['get']['revision'] == e['revision'] and
                    r['get']['start_line'] == e['start_line'] and r['get']['end_line'] == e['end_line']
                    for r in receipts) for e in lineage):
                states[backend] = 'reviewed_lineage_excluded'
            else:
                states[backend] = 'unknown'
        if 'unknown' in states.values():
            all_conclusive = False
        if states['legacy'].endswith('_support') and states['unified'] == 'reviewed_lineage_excluded':
            lost.append({'claim_sha256': claim_id,
                         'evidence_origins': len({e['origin_sha256'] for e in lineage}),
                         'reason': 'public-only exclusion within reviewed equivalence scope'})
        outcomes.append({'claim_sha256': claim_id, **states,
                         'probe_observations': {backend: sorted({
                             'ranking_miss' if r['query']['status'] == 'empty' else
                             'candidate_only' if r['query']['status'] == 'ok' and 'get' not in r else
                             'query_'+r['query']['status'] for r in receipts})
                             for backend, receipts in paired.items()}})
    scope = payload['review_scope']
    measured = bool(scope and scope['equivalent_evidence_complete'] and all_conclusive)
    return {'status': 'measured' if measured else 'not_assessed',
            'count': len(lost) if measured else None,
            'unique_facts': lost if measured else [],
            'reviewed_unique_claims': len(groups), 'claim_outcomes': outcomes,
            'descriptive_source_count': len(payload['descriptive_probe_inventory']),
            'scope_sha256': scope['scope_sha256'] if scope else None,
            'equivalence_completeness_basis': 'Explicit reviewer attestation only; never inferred from source-line counts or searches.',
            'reason': ('Reviewed canonical claims only; not global corpus absence or answer correctness.' if measured else
                       'No complete, conclusive reviewed semantic-equivalence inventory; source lines/probes are not unique facts.'),
            'orphaned_fact_count': None}


def write_new_inventory(path, payload):
    """Exclusive create preserves every old receipt, including historical v1 files."""
    fd = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(payload, stream, indent=2)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--partition', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New private receipt; never overwritten')
    parser.add_argument('--source', action='append', help='Canonical source ID within a supplied registry namespace')
    args = parser.parse_args(argv)
    payload = build_inventory(registry_path=args.registry, partition=args.partition, source_ids=args.source)
    _validate(payload, registry_path=args.registry, partition=args.partition)
    write_new_inventory(args.output, payload)
    print(json.dumps({'output': str(args.output), 'version': 2, 'reviewed_claims': 0,
                      'described_sources': len(payload['descriptive_probe_inventory']),
                      'unique_facts_lost': {'status': 'not_assessed', 'count': None}}))


if __name__ == '__main__':
    main()
