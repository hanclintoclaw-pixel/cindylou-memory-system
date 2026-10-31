#!/usr/bin/env python3
"""Trusted, explicitly scoped readers for the isolated paired U2 experiment.

Legacy campaign measures the full operator corpus, NOT public-authorized results.
Only approved section evidence may leave the private collector. No live native CLI
is launched. Rules/equipment use unchanged production functions through the shared
specialist adapter; only the unified side exercises MemoryService routing.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE))
sys.dont_write_bytecode = True
LEGACY_ROOT = Path('/Users/hanclaw/claw/projects/cindylou/memory-system')
CONTROL = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')
PAGE_CACHE_PATH = Path('/Volumes/carbonite/claw/data/cindylou/cache/sr3data/pdf_page_text.json')
# Experimental candidate filter, not an answer gate or deployment recommendation.
UNIFIED_MIN_SCORE = 0.30


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError('unable to load specialist')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def content_snapshot(paths):
    """Fresh content hashes, including explicit missing dependencies; never cached."""
    rows = []
    for path in sorted(set(map(Path, paths))):
        try:
            before = path.stat()
            raw = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise RuntimeError('source changed while fingerprinting')
            revision = hashlib.sha256(raw).hexdigest()
        except FileNotFoundError:
            revision = 'missing'
        rows.append([str(path), revision])
    return rows


def unavailable(reason, backend='excluded'):
    return {'version': 1, 'status': 'unavailable', 'results': [], 'coverage': 'partial',
            'backends': [{'id': backend, 'status': 'unavailable', 'reason': reason}]}


def passage_receipt(case, hit, payload):
    """No passage text persisted: exact receipt checked in-memory against the rubric."""
    terms = case.get('required_source_terms', [])
    text = payload.get('text', '')
    matched = [term in text for term in terms]
    return {'status': payload.get('status', 'unavailable'), 'doc_id': hit['doc_id'],
            'revision': payload.get('revision'), 'source_line': payload.get('source_line'),
            'lines_returned': payload.get('lines_returned'),
            'passage_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'required_terms_sha256': _digest(terms), 'required_terms_present': matched,
            'supports_required_fact': bool(terms) and all(matched),
            'scope': payload.get('scope', 'approved-section')}


class LegacyReaders:
    """Full-corpus operator baseline: private measurement, not a public service."""

    def __init__(self, *, bridge=None, equip=None, specialists=None):
        sys.path.insert(0, str(LEGACY_ROOT))
        self.bridge = bridge or _load('shadow_legacy_bridge', LEGACY_ROOT/'05_serving/memory_bridge.py')
        self.equip = equip or _load('shadow_legacy_equip', LEGACY_ROOT/'scripts/equip_query.py')
        self.memory_root = Path(self.bridge.MEMORY_ROOT)
        if specialists is None:
            from unification.specialists import SpecialistReaders
            specialists = SpecialistReaders(self.bridge, self.equip, page_cache_path=PAGE_CACHE_PATH)
        self.specialists = specialists

    def _resolve(self, doc_id):
        file_id = doc_id.split('#', 1)[0]
        if file_id.startswith('wiki/'):
            root, rel = Path(self.bridge.CAMPAIGN_WIKI_ROOT), file_id[5:]
        elif file_id.startswith('workspace/'):
            root, rel = Path(self.bridge.WORKSPACE_ROOT), file_id[10:]
        else:
            root, rel = self.memory_root, file_id
        path = root/rel
        if Path(rel).is_absolute() or any(p in {'.', '..'} for p in Path(rel).parts) or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('invalid authoritative namespace')
        return path

    def _file_revision(self, doc_id):
        try:
            return hashlib.sha256(self._resolve(doc_id).read_bytes()).hexdigest()
        except FileNotFoundError:
            return None

    def get(self, doc_id, context, *, revision=None, start_line=1, lines=80):
        context.check()
        if type(start_line) is not int or start_line < 1 or type(lines) is not int or not 1 <= lines <= 200:
            raise ValueError('invalid bounded read')
        path = self._resolve(doc_id)
        current = self._file_revision(doc_id)
        if revision is not None and revision != current:
            return {'status': 'stale'}
        # Production get has a character cap, not line bounds. Read its complete
        # result then derive a bounded receipt; no claim of a bounded legacy API.
        got = self.bridge.get_doc(doc_id, max_chars=path.stat().st_size + 1)
        if Path(got['path']).resolve() != path.resolve() or self._file_revision(doc_id) != current:
            return {'status': 'stale'}
        text = '\n'.join(got['content'].splitlines()[start_line-1:start_line-1+lines])[:16000]
        context.check()
        return {'status': 'ok', 'revision': current, 'text': text, 'source_line': start_line,
                'lines_returned': len(text.splitlines()), 'scope': 'operator-baseline-only'}

    def run(self, case, context):
        context.check()
        adapter = case['adapter']
        if adapter == 'native-operator':
            return unavailable('excluded: live CLI can write recall/index state; no snapshot authority configured')
        if adapter in {'rules', 'equipment'}:
            return self.specialists.run(adapter, case['query'], context, limit=3)
        if adapter != 'campaign':
            raise ValueError('unknown adapter')
        hits = self.bridge.keyword_search(query=case['query'], scope='campaign', limit=5)
        results = [{'doc_id': h.doc_id, 'revision': self._file_revision(h.doc_id),
                    'score': h.score, 'edition_tag': h.edition_tag} for h in hits]
        response = {'version': 1, 'status': 'ok' if results else 'empty', 'results': results,
                    'coverage': 'complete', 'measurement_authority': 'operator-baseline-only',
                    'backends': [{'id': 'legacy-campaign', 'status': 'ready'}]}
        if case.get('required_source_terms'):
            response['passage_evidence'] = [passage_receipt(case, hit, self.get(
                hit['doc_id'], context, revision=hit['revision'], start_line=1, lines=200))
                for hit in results if hit['doc_id'] == case['expected_doc']]
        context.check()
        return response

    def fingerprint(self):
        inventory = content_snapshot(list(self.bridge._iter_docs('campaign')) +
                                     list(self.bridge._iter_docs('sr3_rules')) +
                                     [LEGACY_ROOT/'05_serving/memory_bridge.py',
                                      LEGACY_ROOT/'config/pipeline_paths.py'])
        specialists = self.specialists.fingerprint()
        return {'corpus_sha256': _digest([inventory, specialists]),
                'revisions_sha256': _digest([inventory, specialists]),
                'measurement_scope': 'full-corpus',
                'domains': {'campaign': 'operator-full-corpus', 'rules': 'full-sr3-specialist',
                            'equipment': 'full-tiered-specialist'}, 'specialists': specialists}


class UnifiedReader:
    def __init__(self, legacy, *, registry_path, partition, client_factory=None, min_score=UNIFIED_MIN_SCORE):
        from unification.registry import load_registry
        from unification.service import MemoryService
        self.registry_path, self.partition = Path(registry_path), Path(partition)
        self._client = None
        self._legacy, self.min_score = legacy, min_score
        self._client_factory = client_factory or (lambda: __import__(
            'unification.native_client', fromlist=['NativeClient']).NativeClient(
                self.registry_path, self.partition, min_score=min_score))
        self._service = MemoryService(load_registry(self.registry_path), specialists=legacy.specialists)

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory()
            self._service.native = self._client
        return self._client

    def run(self, case, context):
        context.check()
        adapter = case['adapter']
        if adapter in {'rules', 'equipment'}:
            return self._service.search(case['query'], context, limit=3, domain=adapter, mode='specialist')
        if adapter != 'campaign':
            return unavailable('live operator authority excluded from isolated public experiment')
        self._get_client()
        result = self._service.search(case['query'], context, limit=5, domain='campaign', mode='hybrid')
        if case.get('required_source_terms'):
            result['passage_evidence'] = [passage_receipt(case, hit, self._client.get(
                hit['doc_id'], context, revision=hit['revision'], start_line=1, lines=200))
                for hit in result['results']
                if hit.get('doc_id', '').split('#')[0] == case['expected_doc']]
        return result

    def fingerprint(self):
        from unification.native_client import validate_generation
        manifest = json.loads((self.partition/'partition.json').read_text())
        validate_generation(self.registry_path, self.partition, manifest)
        dependencies = ['service.py','policy.py','registry.py','partition.py','specialists.py',
                        'native_client.py','native_adapter.mjs','native_contract.mjs']
        rows = content_snapshot([self.registry_path, self.partition/'partition.json',
                                 self.partition/'openclaw.json'] +
                                [WORKTREE/'unification'/name for name in dependencies])
        specialists = self._legacy.specialists.fingerprint()
        return {'corpus_sha256': _digest([rows, specialists]),
                'revisions_sha256': _digest([rows, specialists]),
                'measurement_scope': 'small-reviewed-partition',
                'domains': {'campaign': 'small-reviewed-public-partition', 'rules': 'full-sr3-specialist',
                            'equipment': 'full-tiered-specialist'},
                'specialists': specialists, 'candidate_min_score': self.min_score,
                'registry_path': str(self.registry_path), 'partition_path': str(self.partition)}

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None


def create_adapters(args):
    from unification.native_client import validate_generation
    registry_path, partition = Path(args.registry), Path(args.partition)
    validate_generation(registry_path, partition, json.loads((partition/'partition.json').read_text()))
    inventory = None
    if getattr(args, 'fact_inventory', None):
        from scripts.memory_unification_fact_review import load_fact_inventory
        inventory = load_fact_inventory(args.fact_inventory, registry_path=registry_path, partition=partition)
    legacy = LegacyReaders()
    unified = UnifiedReader(legacy, registry_path=registry_path, partition=partition)
    import atexit
    atexit.register(unified.close)
    return {'legacy': legacy, 'unified': unified, 'fact_inventory': inventory}
