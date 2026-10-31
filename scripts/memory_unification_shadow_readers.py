#!/usr/bin/env python3
"""Trusted local readers for the paired U2 shadow run (scripts/memory_unification_shadow.py).

Read-only by construction. Nothing here starts, stops, restarts or reconciles a
service, writes production state, or changes any configuration. The embedding
endpoint is used only by the already-validated isolated partition through the
pinned adapter; this module never talks to it directly.

Deviations from the live caller path, stated explicitly (all read-preserving):

* Legacy retrieval calls the real production functions in process
  (`memory_bridge.keyword_search`, `memory_bridge.page_answer`,
  `equip_query.search`/`corroborate`) instead of forking the CLI. Same ranking
  code, no argparse layer.
* The equipment PDF page cache is loaded from its real path but NEVER saved.
  `save_page_cache` is never called, so the production cache bytes cannot move.
* `openclaw memory search` is the only subprocess, matching the pinned U0 probe
  exactly. It is the live OPERATOR index, so it is measured on the legacy side
  only; the unified side reports it out of scope rather than impersonating it.

Unified is the persistent adapter over the reviewed public partition. Specialists
(rules/equipment) have no unified backend yet, per ADAPTER-DESIGN ("their adapters
are the next step after this one"), so they report `unavailable` with a reason
instead of silently answering from the wrong corpus.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))
LEGACY_ROOT = Path('/Users/hanclaw/claw/projects/cindylou/memory-system')
CONTROL = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')
PILOT_PARTITION = CONTROL/'native-public-pilot-20261031c'
PILOT_REGISTRY = CONTROL/'registry.pilot.json'
PAGE_CACHE_PATH = Path('/Volumes/carbonite/claw/data/cindylou/cache/sr3data/pdf_page_text.json')
UNIFIED_MIN_SCORE = 0.30  # Provisional boundary threshold, evidence and honest limits:
# Measured on the reviewed one-document partition (probe 2026-10-31, 12 nonsense +
# 8 real-content probes). Junk top scores 0.230-0.378; real top scores 0.366-0.557.
# THE DISTRIBUTIONS OVERLAP: one junk probe scored 0.378, above the lowest real hit
# at 0.366, so no threshold separates them cleanly. At 0.30 the observed tradeoff is
# 11/12 junk filtered and 0/8 real hits clipped - the best available point, not a
# clean gate. Raise it and real answers start disappearing; lower it and the Zzyzx
# nonsense case (0.230) returns. Corpus-conditional on 1 approved document; needs
# recalibration against the full public partition before any cutover claim.
# This is boundary ordering-contract enforcement, NOT answer confidence. The
# validated pilot CONFIG is unchanged (query.minScore stays 0); the client passes
# this per request and the adapter enforces it via enforceMinimumScore.

if str(LEGACY_ROOT) not in sys.path:  # the bridge resolves config.pipeline_paths itself
    sys.path.insert(0, str(LEGACY_ROOT))


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                      default=str).encode()).hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Revisions:
    """Content revisions for legacy file hits, so citations can be compared honestly."""

    def __init__(self):
        self._cache = {}

    def of(self, path):
        key = str(path)
        if key not in self._cache:
            try:
                self._cache[key] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            except OSError:
                self._cache[key] = None
        return self._cache[key]


class LegacyReaders:
    """Real production retrieval, in process, read-only."""

    def __init__(self):
        self.bridge = _load('shadow_legacy_bridge', LEGACY_ROOT/'05_serving/memory_bridge.py')
        self.equip = _load('shadow_legacy_equip', LEGACY_ROOT/'scripts/equip_query.py')
        self.memory_root = Path(self.bridge.MEMORY_ROOT)
        self.revisions = _Revisions()
        self.page_cache = self._load_page_cache()
        self._fingerprint = None

    def _load_page_cache(self):
        # Read the real cache; never written back. Missing cache degrades tier exactly
        # as the live tool degrades when a page cannot be corroborated.
        try:
            return json.loads(PAGE_CACHE_PATH.read_text())
        except (OSError, ValueError):
            return {}

    def _file_revision(self, doc_id: str, scope_root_hints=()):
        candidates = []
        for hint in scope_root_hints:
            candidates.append(Path(hint)/doc_id)
        candidates.append(self.memory_root/doc_id)
        for path in candidates:
            if path.is_file():
                return self.revisions.of(path)
        return None

    def _envelope(self, status, results, backend, **fields):
        return {'version': 1, 'status': status, 'results': results, 'coverage': 'complete',
                'backends': [{'id': backend, 'status': 'ready'}], **fields}

    def run(self, case, context):
        context.check()
        adapter = case['adapter']
        if adapter == 'campaign':
            hits = self.bridge.keyword_search(query=case['query'], scope='campaign', limit=5)
            results = [{'doc_id': h.doc_id, 'revision': self._file_revision(h.doc_id),
                        'score': h.score, 'edition_tag': h.edition_tag} for h in hits]
            return self._envelope('ok' if results else 'empty', results, 'legacy-campaign')
        if adapter == 'rules':
            answer = self.bridge.page_answer(query=case['query'], limit=3, min_responsive_books=2)
            results = [{'doc_id': h.doc_id, 'revision': self._file_revision(h.doc_id),
                        'score': h.score, 'citation': h.citation(), 'printed_page': h.printed_page}
                       for h in answer.hits[:3]]
            return self._envelope('ok' if results else 'empty', results, 'legacy-rules',
                                  accepted=answer.accepted, decline_reason=answer.reason,
                                  responsive_books=answer.responsive_books)
        if adapter == 'equipment':
            raw = self.equip.search(case['query'], None, 20)
            for hit in raw:
                self.equip.corroborate(hit, self.page_cache)  # in-memory cache only; never saved
            order = self.equip.TIER_ORDER
            shown = sorted([h for h in raw if order.index(h.tier) <= order.index('WEAK')],
                           key=lambda h: order.index(h.tier))[:3]
            results = [{'doc_id': f"sr3data:{h.dataset}/{h.name}", 'revision': None,
                        'name': h.name, 'tier': h.tier, 'cite': h.cite, 'fields': h.fields}
                       for h in shown]
            return self._envelope('ok' if results else 'empty', results, 'legacy-equipment',
                                  blocked_count=len(raw) - len(shown))
        if adapter == 'native-operator':
            # Identical to the pinned U0 probe. Live operator index, legacy side only.
            run = subprocess.run(['openclaw', 'memory', 'search', '--agent', 'cindylou', '--json',
                                  '--max-results', '3', case['query']], capture_output=True,
                                 text=True, timeout=35, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            try:
                payload = json.loads(run.stdout)
            except ValueError:
                return {'version': 1, 'status': 'unavailable', 'results': [], 'coverage': 'partial',
                        'backends': [{'id': 'legacy-native-operator', 'status': 'unavailable',
                                      'reason': 'invalid_json'}]}
            results = [{'doc_id': h.get('path'), 'revision': None, 'score': h.get('score'),
                        'source': h.get('source')} for h in payload.get('results', [])]
            if run.returncode != 0:
                return {'version': 1, 'status': 'unavailable', 'results': [], 'coverage': 'partial',
                        'backends': [{'id': 'legacy-native-operator', 'status': 'unavailable',
                                      'reason': f'exit_{run.returncode}'}]}
            return self._envelope('ok' if results else 'empty', results, 'legacy-native-operator')
        raise ValueError(f'unknown adapter {adapter}')

    def fingerprint(self):
        if self._fingerprint is None:
            inventory = []
            for scope in ('campaign', 'sr3_rules'):
                for path in self.bridge._iter_docs(scope):
                    try:
                        stat = path.stat()
                        inventory.append([str(path), stat.st_size, stat.st_mtime_ns])
                    except OSError:
                        continue
            for path in (self.equip.DB_PATH, PAGE_CACHE_PATH):
                try:
                    stat = path.stat()
                    inventory.append([str(path), stat.st_size, stat.st_mtime_ns])
                except OSError:
                    continue
            if not inventory:
                raise RuntimeError('legacy corpus is not reachable')
            self._fingerprint = {
                'corpus_sha256': _digest(sorted(inventory)),
                'revisions_sha256': _digest(sorted({row[0] for row in inventory})),
                'measurement_scope': 'full-corpus'}
        return dict(self._fingerprint)


class UnifiedReader:
    """Persistent pinned adapter for campaign; specialists wrapped per PLAN U2.

    Rules/equipment are wrapped EXISTING specialists (memory_bridge.page_answer,
    equip_query.search/corroborate) inside the shared envelope — decision logic
    and printed-page numbers untouched, distinct backend ids, no raw-score
    merging. They are the unified path for those domains until a native
    corpus exists there; the wrapping itself is what U2 requires.
    """

    OUT_OF_SCOPE = {
        'native-operator': 'live operator index is out of scope for the public-only partition',
    }

    def __init__(self, legacy: 'LegacyReaders', client_factory=None):
        self._client = None
        self._legacy = legacy
        self._client_factory = client_factory or (lambda: __import__(
            'unification.native_client', fromlist=['NativeClient']).NativeClient(
                PILOT_REGISTRY, PILOT_PARTITION, min_score=UNIFIED_MIN_SCORE))

    def _get_client(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _unavailable(self, reason):
        return {'version': 1, 'status': 'unavailable', 'results': [], 'coverage': 'partial',
                'backends': [{'id': 'openclaw', 'status': 'unavailable', 'reason': reason}]}

    def _wrapped_rules(self, case):
        # Same production call as legacy, re-enveloped. No re-scoring, no re-ranking.
        answer = self._legacy.bridge.page_answer(query=case['query'], limit=3,
                                                 min_responsive_books=2)
        results = [{'doc_id': h.doc_id,
                    'revision': self._legacy._file_revision(h.doc_id),
                    'score': h.score, 'citation': h.citation(), 'printed_page': h.printed_page}
                   for h in answer.hits[:3]]
        return {'version': 1, 'status': 'ok' if results else 'empty', 'results': results,
                'coverage': 'complete',
                'backends': [{'id': 'rules-specialist-wrapped', 'status': 'ready'}],
                'accepted': answer.accepted, 'decline_reason': answer.reason,
                'responsive_books': answer.responsive_books}

    def _wrapped_equipment(self, case):
        raw = self._legacy.equip.search(case['query'], None, 20)
        for hit in raw:
            self._legacy.equip.corroborate(hit, self._legacy.page_cache)  # never saved
        order = self._legacy.equip.TIER_ORDER
        shown = sorted([h for h in raw if order.index(h.tier) <= order.index('WEAK')],
                       key=lambda h: order.index(h.tier))[:3]
        results = [{'doc_id': f"sr3data:{h.dataset}/{h.name}", 'revision': None,
                    'name': h.name, 'tier': h.tier, 'cite': h.cite, 'fields': h.fields}
                   for h in shown]
        return {'version': 1, 'status': 'ok' if results else 'empty', 'results': results,
                'coverage': 'complete',
                'backends': [{'id': 'equipment-specialist-wrapped', 'status': 'ready'}],
                'blocked_count': len(raw) - len(shown)}

    def run(self, case, context):
        context.check()
        adapter = case['adapter']
        if adapter in self.OUT_OF_SCOPE:
            return self._unavailable(self.OUT_OF_SCOPE[adapter])
        if adapter == 'rules':
            return self._wrapped_rules(case)
        if adapter == 'equipment':
            return self._wrapped_equipment(case)
        if adapter != 'campaign':
            return self._unavailable(f'adapter {adapter!r} has no unified backend')
        try:
            result = self._get_client().search(case['query'], context, 5)
        except Exception as error:
            return self._unavailable(f'native client error: {type(error).__name__}')
        if result.get('status') not in {'ok', 'empty', 'stale', 'unavailable', 'denied'}:
            return self._unavailable('invalid native envelope')
        return result

    def fingerprint(self):
        # Campaign half is the reviewed partition; wrapped specialists run over the
        # same full corpus as legacy. Scope reports the smaller (dominant) surface.
        manifest = json.loads((PILOT_PARTITION/'partition.json').read_text())
        rows = sorted([r['evidence']['doc_id'], r['evidence']['revision'], r['sha256']]
                      for r in manifest['records'])
        return {'corpus_sha256': _digest([rows, 'wrapped-specialists']),
                'revisions_sha256': _digest(rows),
                'measurement_scope': 'small-reviewed-partition'}

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None


def _load_fact_inventory():
    # Harness contract: reviewed rows with opaque hashes only, never fact text.
    # Absent review reports 'unavailable' through the harness; nothing is fabricated.
    path = CONTROL/'shadow-fact-review.private.json'
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    if payload.get('reviewer') != 'cindylou-local-review':
        raise ValueError('fact inventory requires a completed local review')
    return {'reviewed': True, 'records': payload['records']}


def create_adapters(args):
    legacy = LegacyReaders()
    unified = UnifiedReader(legacy)
    import atexit
    atexit.register(unified.close)
    return {'legacy': legacy, 'unified': unified,
            'fact_inventory': _load_fact_inventory()}
