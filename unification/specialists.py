"""Trusted, off-live-path SR3 specialist routes for the shared MemoryService.

The constructor is a host-owned public-source grant, not caller JSON. It accepts
the reviewed production modules, keeps their ranking/admission functions, and
limits their data scope to the existing rules corpus and equipment references.
No campaign registry approvals are inferred or changed. This is not a sandbox
for arbitrary injected Python: backend code and data generations are recorded.

Equipment functions have private cloned globals, an immutable read-only SQLite
facade, and a disabled cache saver. PDF extraction may populate only the request's
in-memory cache. A live WAL is refused (immutable SQLite would ignore its rows).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import types

from .policy import AccessContext, AccessDenied, StaleReference


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _revision(path: Path):
    try:
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
    except FileNotFoundError:
        return None
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise StaleReference('specialist source changed during read')
    return hashlib.sha256(raw).hexdigest()


class _ReadOnlySQLite:
    """Per-adapter facade: never modify the process-wide sqlite3 module."""
    Row = sqlite3.Row

    def __init__(self, database: Path):
        self.database = database.resolve()

    def connect(self, database, *args, **kwargs):
        if Path(database).resolve() != self.database or args or kwargs:
            raise ValueError('unexpected specialist SQLite connection')
        if not self.database.is_file():
            raise FileNotFoundError('equipment database unavailable')
        wal = Path(str(self.database) + '-wal')
        if wal.exists() and wal.stat().st_size:
            raise RuntimeError('equipment WAL requires a controlled snapshot')
        connection = sqlite3.connect(self.database.as_uri() + '?mode=ro&immutable=1', uri=True)
        connection.execute('PRAGMA query_only = ON')
        return connection


def _read_only_equipment(module):
    """Clone function globals so existing production callables remain untouched."""
    namespace = dict(vars(module))
    namespace['sqlite3'] = _ReadOnlySQLite(Path(module.DB_PATH))

    def no_save(*args, **kwargs):
        raise RuntimeError('production cache writes disabled in the specialist adapter')

    for name, fn in list(namespace.items()):
        if isinstance(fn, types.FunctionType) and fn.__globals__ is vars(module):
            clone = types.FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, fn.__closure__)
            clone.__kwdefaults__ = fn.__kwdefaults__
            namespace[name] = clone
    namespace['save_page_cache'] = no_save
    return types.SimpleNamespace(**namespace)


class SpecialistReaders:
    """Trusted injection of unchanged SR3 specialists, with explicit public scope.

    `allowed_audiences` is transport configuration, never a query parameter.
    Public SR3 evidence is readable in any valid audience by default, but context
    currency is checked before I/O and again before releasing any evidence.
    """
    def __init__(self, bridge, equip, *, page_cache_path: Path | None = None,
                 allowed_audiences=('public', 'gm', 'operator', 'conversation')):
        self.bridge = bridge
        self.equip = _read_only_equipment(equip)
        self.page_cache_path = Path(page_cache_path or equip.PAGE_CACHE)
        self.allowed_audiences = frozenset(allowed_audiences)
        if not self.allowed_audiences <= {'public', 'gm', 'operator', 'conversation'}:
            raise ValueError('invalid specialist audience grant')
        code_paths = {Path(m.__file__).resolve() for m in (bridge, equip)}
        for path in tuple(code_paths):
            dependency = path.parent.parent/'config/pipeline_paths.py'
            if dependency.is_file():
                code_paths.add(dependency)
        self._code_paths = tuple(sorted(code_paths))
        self._loaded_code = {str(path): _revision(path) for path in self._code_paths}
        if any(revision is None for revision in self._loaded_code.values()):
            raise FileNotFoundError('specialist backend code unavailable')

    def source_paths(self, domain: str | None = None):
        if domain not in {None, 'rules', 'equipment'}:
            raise ValueError('unsupported specialist domain')
        paths = set(self._code_paths)
        for path in self._code_paths:
            # pipeline_paths is a backend dependency, not a production mutation.
            root = path.parent.parent
            dependency = root/'config/pipeline_paths.py'
            if dependency.is_file():
                paths.add(dependency)
        if domain in {None, 'rules'}:
            root = Path(self.bridge.MEMORY_ROOT)/'00_sources/rules_references'
            paths.update(root.rglob('*.md'))
        if domain in {None, 'equipment'}:
            db = Path(self.equip.DB_PATH)
            paths.update((db, Path(str(db)+'-wal'), Path(str(db)+'-shm'), self.page_cache_path))
            for relatives in self.equip.TEXT_LAYER_PDFS.values():
                paths.update(Path(self.equip.PDF_ROOT)/relative for relative in relatives)
        return sorted(paths)

    def _snapshot(self, domain):
        rows = {str(path): _revision(path) for path in self.source_paths(domain)}
        if any(rows[str(path)] != revision for path, revision in self._loaded_code.items()):
            raise StaleReference('loaded specialist backend code changed')
        return {'generation_sha256': _digest(rows), 'source_revisions': rows,
                'backend_version': _digest(self._loaded_code),
                'measurement_scope': 'full-sr3-specialist-corpus',
                'visibility': 'public', 'domain': domain}

    def fingerprint(self):
        return {domain: self._snapshot(domain) for domain in ('rules', 'equipment')}

    @staticmethod
    def _envelope(domain, status, results, snapshot=None, **extra):
        backend = {'id': domain+'-specialist-wrapped',
                   'status': 'unavailable' if status == 'unavailable' else 'ready'}
        if snapshot is not None:
            backend.update(snapshot)
        if 'reason' in extra:
            backend['reason'] = extra['reason']
        return {'version': 1, 'status': status, 'results': results,
                'coverage': 'partial' if status == 'unavailable' else 'complete',
                'backends': [backend], 'domain': domain, 'mode': 'specialist', **extra}

    def run(self, domain: str, query: str, ctx: AccessContext, limit: int = 3):
        ctx.check()
        if ctx.audience not in self.allowed_audiences:
            raise AccessDenied('not authorized')
        if domain not in {'rules', 'equipment'}:
            raise ValueError('unsupported specialist domain')
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError('query must contain 1..4000 characters')
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError('limit must be 1..30')
        try:
            before = self._snapshot(domain)
            if domain == 'rules':
                result = self._rules(query, limit, before)
            else:
                result = self._equipment(query, limit, before)
            after = self._snapshot(domain)
            if before != after:
                raise StaleReference('specialist source generation changed')
        except (AccessDenied, StaleReference):
            raise
        except (Exception, SystemExit) as error:
            # SystemExit is the production equipment module's missing-DB signal.
            # Never expose internal paths/exception text to a public response.
            result = self._envelope(domain, 'unavailable', [], reason=type(error).__name__)
        ctx.check()
        return result

    def _rules(self, query, limit, snapshot):
        rules_root = Path(self.bridge.MEMORY_ROOT)/'00_sources/rules_references'
        if not rules_root.is_dir() or not any(rules_root.rglob('*.md')):
            return self._envelope('rules', 'unavailable', [], snapshot, reason='rules corpus unavailable')
        answer = self.bridge.page_answer(query=query, limit=limit, min_responsive_books=2)
        results = []
        for hit in answer.hits[:limit]:
            path = (Path(self.bridge.MEMORY_ROOT)/hit.doc_id).resolve()
            if not path.is_relative_to(rules_root.resolve()):
                raise AccessDenied('not authorized')
            revision = snapshot['source_revisions'].get(str(path))
            if revision is None:
                raise StaleReference('rules hit has no bound source revision')
            results.append({'doc_id': hit.doc_id, 'revision': revision,
                            'domain': 'rules', 'backend_version': snapshot['backend_version'],
                            'score': hit.score, 'excerpt': hit.snippet,
                            'citation': hit.citation(), 'printed_page': hit.printed_page,
                            'marker_page': hit.marker_page, 'edition_tag': hit.edition_tag,
                            'visibility': 'public', 'authority': 'SR3 rules specialist',
                            'admitted': bool(answer.accepted)})
        return self._envelope('rules', 'ok' if answer.accepted else 'decline', results, snapshot,
                              accepted=answer.accepted, decline_reason=answer.reason,
                              responsive_books=answer.responsive_books)

    def _equipment(self, query, limit, snapshot):
        db = Path(self.equip.DB_PATH)
        wal = Path(str(db)+'-wal')
        if wal.exists() and wal.stat().st_size:
            return self._envelope('equipment', 'unavailable', [], snapshot,
                                  reason='equipment WAL requires a controlled snapshot')
        try:
            page_cache = json.loads(self.page_cache_path.read_text())
        except FileNotFoundError:
            page_cache = {}  # Same documented production missing-cache degradation.
        if not isinstance(page_cache, dict):
            raise ValueError('invalid equipment page cache')
        raw = self.equip.search(query, None, 20)
        for hit in raw:
            self.equip.corroborate(hit, page_cache)
        order = self.equip.TIER_ORDER
        eligible = sorted([h for h in raw if order.index(h.tier) <= order.index('WEAK')],
                          key=lambda h: order.index(h.tier))
        results = []
        revision = snapshot['source_revisions'].get(str(db))
        if revision is None:
            raise FileNotFoundError('equipment database unavailable')
        for hit in eligible[:limit]:
            results.append({'doc_id': f'sr3data:{hit.dataset}/{hit.name}', 'revision': revision,
                            'domain': 'equipment', 'backend_version': snapshot['backend_version'],
                            'name': hit.name, 'tier': hit.tier, 'cite': hit.cite,
                            'fields': hit.fields, 'why': hit.why,
                            'verified_tokens': hit.verified_tokens, 'missing_tokens': hit.missing_tokens,
                            'source_kind': hit.source_kind, 'book_code': hit.book_code,
                            'fan_published': hit.book_code in getattr(self.equip, 'FAN_ERA_CODES', set()),
                            'gm_permission_required': hit.book_code in getattr(self.equip, 'FAN_ERA_CODES', set()),
                            'printed_page': hit.page, 'visibility': 'public',
                            'authority': 'SR3 equipment specialist'})
        return self._envelope('equipment', 'ok' if results else 'decline', results, snapshot,
                              blocked_count=len(raw)-len(eligible), eligible_count=len(eligible),
                              truncated=len(eligible)>limit)
