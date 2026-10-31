"""Private/provisional durable capture authority, not a live caller integration.

Immutable, revision-checked JSON records plus a monotonically growing identity
inventory are canonical. Missing/changed inventoried records fail closed even
when SQLite is lost. SQLite token postings and receipts are rebuildable and
committed together; a durable save is not called
searchable until that transaction succeeds. No capture input can promote a claim
or make it public. Trusted host contexts alone authorize operator/GM access.

An exclusive process lock covers saves, idempotency, corrections and recovery.
Atomic file replacement plus file/directory fsync precedes inventory and indexing.
A crash in that gap leaves a validated record that startup/retry adopts and
indexes, never a duplicate. Only genuinely new roots bootstrap an empty inventory.
The database must not be shared with a live service. This library creates no
session authority and does not import or modify any production records.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import shutil
import tempfile
import time
import uuid

from .policy import AccessContext, AccessDenied

SHA256 = re.compile(r'[a-f0-9]{64}\Z')
QUERY_MAX_CHARS = 4000


class CaptureConflict(ValueError):
    """A changed idempotent retry or conflicting correction."""


class CaptureIntegrityError(ValueError):
    """Canonical source or lineage validation failed; fail closed."""


class _IndexSchemaMismatch(ValueError):
    pass


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else _encode(value)).hexdigest()


def _tokens(text):
    return sorted({token for token in re.findall(r'\w+', text.casefold())
                   if any(character.isalnum() for character in token)})


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class CaptureStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.resolve() != self.root or self.root.is_symlink():
            raise ValueError('absolute canonical private capture root required')
        self._bootstrap_root()
        self.records_path = self.root/'records'
        self.records_path.mkdir(mode=0o700, exist_ok=True)
        self.index_path = self.root/'index.sqlite'
        self.lock_path = self.root/'capture.lock'
        self.inventory_path = self.root/'inventory.json'
        for path in (self.root, self.records_path):
            if path.is_symlink() or path.resolve() != path or path.stat().st_mode & 0o077:
                raise ValueError('capture directories must be canonical and private')
        for path in (self.index_path, self.lock_path, self.inventory_path):
            if path.is_symlink():
                raise ValueError('capture control files cannot be symlinks')
        self.recover()

    def _bootstrap_root(self):
        """Publish only a fully initialized root, under a parent-scoped lock."""
        self.root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        bootstrap_lock = self.root.parent/('.capture-bootstrap-'+_sha(str(self.root).encode())+'.lock')
        fd = os.open(bootstrap_lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        stage = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if self.root.exists():
                return  # Missing inventory in an established root remains fatal.
            stage = Path(tempfile.mkdtemp(prefix='.capture-bootstrap-stage-', dir=self.root.parent))
            (stage/'records').mkdir(mode=0o700)
            self._atomic_json_locked(stage/'inventory.json', {'version': 1, 'records': {}})
            _fsync_directory(stage)
            self._publish_bootstrap(stage, self.root)
            stage = None
            _fsync_directory(self.root.parent)
        finally:
            if stage is not None:
                # Only this new, unpublished, empty-source bootstrap directory.
                shutil.rmtree(stage)
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _publish_bootstrap(stage, root):
        os.rename(stage, root)

    @staticmethod
    def _authorize(ctx, visibility=None):
        ctx.check()
        if ctx.audience not in {'operator', 'gm'}:
            raise AccessDenied('not authorized')
        if visibility is not None and (visibility not in {'operator', 'gm'} or
                                     visibility == 'operator' and ctx.audience != 'operator'):
            raise AccessDenied('not authorized')

    @contextmanager
    def _locked(self):
        for path in (self.root, self.records_path):
            if path.is_symlink() or path.resolve() != path or path.stat().st_mode & 0o077:
                raise CaptureIntegrityError('capture directories must remain canonical and private')
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _request(text, origin, visibility, supersedes, derivative_of):
        if not isinstance(text, str) or not text.strip() or len(text) > 32000:
            raise ValueError('capture text must contain 1..32000 characters')
        if not any(len(token) <= QUERY_MAX_CHARS for token in _tokens(text)):
            raise ValueError('capture text must contain an indexable token within the query budget')
        if visibility not in {'operator', 'gm'}:
            raise AccessDenied('not authorized')
        if not isinstance(origin, dict) or set(origin)-{'doc_id', 'revision', 'start_line', 'end_line', 'record_id', 'kind'}:
            raise ValueError('explicit bounded origin evidence required')
        if not isinstance(origin.get('doc_id'), str) or not 1 <= len(origin['doc_id']) <= 4000:
            raise ValueError('origin document identity required')
        if not isinstance(origin.get('revision'), str) or not SHA256.fullmatch(origin['revision']):
            raise ValueError('origin SHA-256 revision required')
        if ('start_line' in origin) != ('end_line' in origin):
            raise ValueError('origin bounds must be paired')
        if 'start_line' in origin and (type(origin['start_line']) is not int or
                                     type(origin['end_line']) is not int or
                                     not 1 <= origin['start_line'] <= origin['end_line']):
            raise ValueError('invalid origin evidence bounds')
        for key in ('record_id', 'kind'):
            if key in origin and (not isinstance(origin[key], str) or not 1 <= len(origin[key]) <= 4000):
                raise ValueError('invalid origin identity')
        for reference in (supersedes, derivative_of):
            if reference is not None and (not isinstance(reference, str) or not SHA256.fullmatch(reference)):
                raise ValueError('invalid capture lineage reference')
        if supersedes is not None and derivative_of is not None:
            raise ValueError('a record is a correction or a derivative, not both')
        return {'text': text, 'origin': dict(origin), 'visibility': visibility,
                'supersedes': supersedes, 'derivative_of': derivative_of}

    def _records_locked(self):
        records = {}
        for path in sorted(self.records_path.glob('*.json')):
            if path.is_symlink() or not SHA256.fullmatch(path.stem) or path.stat().st_mode & 0o077:
                raise CaptureIntegrityError('invalid canonical capture file')
            try:
                record = json.loads(path.read_bytes())
                required = {'version', 'record_id', 'revision', 'request_sha256', 'saved_at_ns',
                            'claim_status', 'evidence_group', 'text', 'origin', 'visibility',
                            'supersedes', 'derivative_of'}
                if not isinstance(record, dict) or set(record) != required:
                    raise ValueError('invalid capture schema')
                request = self._request(**{k: record[k] for k in (
                    'text', 'origin', 'visibility', 'supersedes', 'derivative_of')})
                revision = record['revision']
                if (record['version'] != 1 or record['record_id'] != path.stem or
                    record['request_sha256'] != _sha(request) or record['claim_status'] != 'provisional' or
                    type(record['saved_at_ns']) is not int or record['saved_at_ns'] < 1 or
                    not isinstance(revision, str) or not SHA256.fullmatch(revision) or
                    revision != _sha({k:v for k,v in record.items() if k != 'revision'})):
                    raise ValueError('invalid capture revision')
                records[path.stem] = record
            except (ValueError, TypeError, KeyError) as error:
                raise CaptureIntegrityError('canonical capture validation failed') from error
        corrections = {}
        for record in records.values():
            target = record['supersedes'] or record['derivative_of']
            if target is None:
                expected_group = 'capture:'+record['record_id']
            else:
                original = records.get(target)
                if original is None or target == record['record_id']:
                    raise CaptureIntegrityError('missing capture lineage')
                if original['visibility'] == 'operator' and record['visibility'] != 'operator':
                    raise CaptureIntegrityError('capture lineage visibility widened')
                if record['supersedes'] and original['visibility'] != record['visibility']:
                    raise CaptureIntegrityError('correction visibility differs from original')
                expected_group = original['evidence_group']
                if record['supersedes']:
                    if target in corrections:
                        raise CaptureIntegrityError('competing canonical corrections')
                    corrections[target] = record['record_id']
            if record['evidence_group'] != expected_group:
                raise CaptureIntegrityError('capture evidence group differs from lineage')
            # A chain may not point back at itself, even after owner-side edits.
            seen = {record['record_id']}
            while target is not None:
                if target in seen:
                    raise CaptureIntegrityError('cyclic capture lineage')
                seen.add(target)
                ancestor = records.get(target)
                if ancestor is None:
                    raise CaptureIntegrityError('missing capture lineage')
                target = ancestor['supersedes'] or ancestor['derivative_of']
        self._inventory_locked(records)
        return records

    def _inventory_locked(self, records):
        """Canonical, monotonic identity authority; never rebuilt from SQLite."""
        if self.inventory_path.is_symlink():
            raise CaptureIntegrityError('canonical inventory cannot be a symlink')
        if self.inventory_path.exists():
            if self.inventory_path.stat().st_mode & 0o077:
                raise CaptureIntegrityError('canonical inventory must remain private')
            try:
                inventory = json.loads(self.inventory_path.read_bytes())
                if not isinstance(inventory, dict) or set(inventory) != {'version', 'records'} or inventory['version'] != 1:
                    raise ValueError('invalid inventory schema')
                expected = inventory['records']
                if not isinstance(expected, dict) or any(
                        not isinstance(key, str) or not SHA256.fullmatch(key) or
                        not isinstance(revision, str) or not SHA256.fullmatch(revision)
                        for key, revision in expected.items()):
                    raise ValueError('invalid inventory identities')
            except (ValueError, TypeError) as error:
                raise CaptureIntegrityError('canonical inventory validation failed') from error
        else:
            raise CaptureIntegrityError('established store canonical inventory is missing')
        for record_id, revision in expected.items():
            if record_id not in records or records[record_id]['revision'] != revision:
                raise CaptureIntegrityError('inventoried canonical capture is missing or changed')
        additions = {record_id: record['revision'] for record_id, record in records.items()
                     if record_id not in expected}
        if additions:
            # Validated post-save/pre-inventory crash orphans are adopted. Never
            # delete an identity or change an existing revision in this authority.
            self._atomic_json_locked(self.inventory_path,
                                     {'version': 1, 'records': {**expected, **additions}})

    def _open_index_locked(self):
        if self.index_path.is_symlink():
            raise CaptureIntegrityError('index path is not canonical')
        connection = None
        try:
            connection = sqlite3.connect(self.index_path)
            connection.execute('PRAGMA journal_mode=DELETE')
            connection.execute('PRAGMA synchronous=FULL')
            if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise _IndexSchemaMismatch('index integrity check failed')
            expected = {
                'records': ('record_id', 'revision', 'visibility', 'evidence_group', 'effective_status', 'saved_at_ns', 'indexed_at_ns'),
                'terms': ('record_id', 'term'),
                'receipts': ('record_id', 'revision', 'saved', 'searchable', 'promoted', 'saved_at_ns', 'indexed_at_ns')}
            for name, columns in expected.items():
                present = tuple(row[1] for row in connection.execute('PRAGMA table_info('+name+')'))
                if present and present != columns:
                    raise _IndexSchemaMismatch('incompatible rebuildable index schema')
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS records (
                    record_id TEXT PRIMARY KEY, revision TEXT NOT NULL,
                    visibility TEXT NOT NULL, evidence_group TEXT NOT NULL,
                    effective_status TEXT NOT NULL, saved_at_ns INTEGER NOT NULL,
                    indexed_at_ns INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS terms (
                    record_id TEXT NOT NULL, term TEXT NOT NULL,
                    PRIMARY KEY (record_id, term));
                CREATE INDEX IF NOT EXISTS term_lookup ON terms(term, record_id);
                CREATE TABLE IF NOT EXISTS receipts (
                    record_id TEXT PRIMARY KEY, revision TEXT NOT NULL,
                    saved INTEGER NOT NULL, searchable INTEGER NOT NULL,
                    promoted INTEGER NOT NULL, saved_at_ns INTEGER NOT NULL,
                    indexed_at_ns INTEGER NOT NULL);
            ''')
            os.chmod(self.index_path, 0o600)
            return connection
        except (sqlite3.DatabaseError, _IndexSchemaMismatch) as error:
            if connection is not None:
                connection.close()
            if not isinstance(error, _IndexSchemaMismatch) and getattr(error, 'sqlite_errorcode', None) not in {
                    sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
                raise
            suffix = '.corrupt.'+uuid.uuid4().hex
            for path in (self.index_path, Path(str(self.index_path)+'-journal'),
                         Path(str(self.index_path)+'-wal'), Path(str(self.index_path)+'-shm')):
                if path.exists():
                    os.replace(path, Path(str(path)+suffix))
            _fsync_directory(self.root)
            return self._open_index_locked()

    @staticmethod
    def _effective_statuses(records):
        superseded = {r['supersedes'] for r in records.values() if r['supersedes']}
        stale = {}
        def stale_dependency(record_id):
            if record_id in stale:
                return stale[record_id]
            record = records[record_id]
            if record['derivative_of']:
                target = record['derivative_of']
                value = target in superseded or stale_dependency(target)
            elif record['supersedes']:
                # Corrections retain any inherited derivative dependency, but a
                # corrected primary assertion does not depend on its own old text.
                value = stale_dependency(record['supersedes'])
            else:
                value = False
            stale[record_id] = value
            return value
        return {record_id: ('superseded' if record_id in superseded else
                            'stale-derivative' if stale_dependency(record_id) else 'provisional')
                for record_id in records}

    def _reconcile_locked(self, records):
        connection = self._open_index_locked()
        try:
            old = {row[0]: row[1:] for row in connection.execute(
                'SELECT record_id,revision,indexed_at_ns FROM receipts')}
            statuses = self._effective_statuses(records)
            with connection:
                connection.execute('DELETE FROM records')
                connection.execute('DELETE FROM terms')
                connection.execute('DELETE FROM receipts')
                for record_id, record in records.items():
                    previous = old.get(record_id)
                    indexed = previous[1] if previous and previous[0] == record['revision'] else 0
                    status = statuses[record_id]
                    connection.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?)', (
                        record_id, record['revision'], record['visibility'], record['evidence_group'],
                        status, record['saved_at_ns'], indexed))
                    connection.executemany('INSERT INTO terms VALUES (?,?)',
                                           [(record_id, term) for term in _tokens(record['text'])])
                    connection.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?)', (
                        record_id, record['revision'], 1, 1, 0, record['saved_at_ns'], indexed))
            # Observe searchability AFTER the index+receipt commit, never timestamp
            # it at transaction start. Zero is an internal unknown observation;
            # a crash here is recovered conservatively on the next startup.
            observed = time.time_ns()
            with connection:
                connection.execute('UPDATE records SET indexed_at_ns=? WHERE indexed_at_ns=0', (observed,))
                connection.execute('UPDATE receipts SET indexed_at_ns=? WHERE indexed_at_ns=0', (observed,))
            return {row[0]: {'record_id': row[0], 'revision': row[1], 'saved': bool(row[2]),
                            'searchable': bool(row[3]), 'promoted': bool(row[4]),
                            'saved_at_ns': row[5], 'indexed_at_ns': row[6],
                            'saved_to_searchable_ms': max(0, (row[6]-row[5])/1_000_000)}
                    for row in connection.execute('SELECT * FROM receipts')}
        finally:
            connection.close()

    def recover(self):
        """Host-only recovery; all derived state can be discarded and rebuilt."""
        with self._locked():
            records = self._records_locked()
            receipts = self._reconcile_locked(records)
            return {'saved_records': len(records), 'searchable_records': len(receipts),
                    'promoted_records': 0,
                    'saved_to_searchable_ms': [r['saved_to_searchable_ms'] for r in receipts.values()]}

    def _persist_locked(self, record):
        self._atomic_json_locked(self.records_path/(record['record_id']+'.json'), record)

    @staticmethod
    def _atomic_json_locked(path, payload):
        pending = path.parent/('.pending-'+uuid.uuid4().hex)
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(_encode(payload)+b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, path)
            _fsync_directory(path.parent)
        finally:
            if pending.exists():
                pending.unlink()  # Only this call's private, uncommitted temporary file.

    def capture(self, text: str, ctx: AccessContext, *, idempotency_key: str, origin: dict,
                visibility: str = 'operator', supersedes: str | None = None,
                derivative_of: str | None = None):
        self._authorize(ctx, visibility)
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 4000:
            raise ValueError('explicit idempotency key required')
        request = self._request(text, origin, visibility, supersedes, derivative_of)
        record_id = _sha(['capture-id-v2', visibility, idempotency_key])
        with self._locked():
            self._authorize(ctx, visibility)
            records = self._records_locked()
            created = False
            if record_id in records:
                record = records[record_id]
                self._authorize(ctx, record['visibility'])
                if record['request_sha256'] != _sha(request):
                    raise CaptureConflict('idempotency key already saved different capture')
            else:
                target_id = supersedes or derivative_of
                if target_id is not None:
                    target = records.get(target_id)
                    if target is None:
                        if ctx.audience != 'operator':
                            raise AccessDenied('not authorized')
                        raise CaptureConflict('capture lineage unavailable')
                    self._authorize(ctx, target['visibility'])
                    if target['visibility'] == 'operator' and visibility != 'operator':
                        raise AccessDenied('not authorized')
                    if supersedes and target['visibility'] != visibility:
                        raise AccessDenied('not authorized')
                    if supersedes and any(r['supersedes'] == supersedes for r in records.values()):
                        raise CaptureConflict('capture already has a correction')
                    group = target['evidence_group']
                else:
                    group = 'capture:'+record_id
                record = {'version': 1, 'record_id': record_id, 'request_sha256': _sha(request),
                          'saved_at_ns': time.time_ns(), 'claim_status': 'provisional',
                          'evidence_group': group, **request}
                record['revision'] = _sha(record)
                self._authorize(ctx, visibility)
                self._persist_locked(record)
                created = True
                records[record_id] = record
            try:
                self._inventory_locked(records)
                receipts = self._reconcile_locked(records)
                receipt = receipts[record_id]
            except Exception as error:
                receipt = {'record_id': record_id, 'revision': record['revision'],
                           'saved': True, 'searchable': False, 'promoted': False,
                           'saved_at_ns': record['saved_at_ns'], 'indexed_at_ns': None,
                           'saved_to_searchable_ms': None, 'index_error': type(error).__name__}
            self._authorize(ctx, visibility)
            return {**receipt, 'created': created}

    def search(self, query: str, ctx: AccessContext, *, limit: int = 8, include_superseded=False):
        self._authorize(ctx)
        if not isinstance(query, str) or not query.strip() or len(query) > QUERY_MAX_CHARS:
            raise ValueError('query must contain 1..4000 characters')
        terms = _tokens(query)
        if not terms or len(terms) > 64 or type(limit) is not int or not 1 <= limit <= 30 or type(include_superseded) is not bool:
            raise ValueError('invalid capture search bounds')
        with self._locked():
            records = self._records_locked()
            self._reconcile_locked(records)
            connection = self._open_index_locked()
            try:
                placeholders = ','.join('?' for _ in terms)
                audience = "r.visibility IN ('operator','gm')" if ctx.audience == 'operator' else "r.visibility = 'gm'"
                current = '' if include_superseded else "AND r.effective_status = 'provisional'"
                rows = list(connection.execute(f'''
                    SELECT r.record_id, r.effective_status FROM records r
                    JOIN terms t ON t.record_id=r.record_id
                    WHERE {audience} {current} AND t.term IN ({placeholders})
                    GROUP BY r.record_id HAVING COUNT(DISTINCT t.term)=?
                    ORDER BY r.saved_at_ns DESC, r.record_id LIMIT ?
                ''', [*terms, len(terms), limit]))
            finally:
                connection.close()
            self._authorize(ctx)
            return {'version': 1, 'status': 'ok' if rows else 'empty', 'promoted': False,
                    'results': [{**records[record_id], 'effective_status': status} for record_id, status in rows]}

    def history(self, record_id: str, ctx: AccessContext):
        self._authorize(ctx)
        if not isinstance(record_id, str) or not SHA256.fullmatch(record_id):
            raise ValueError('invalid capture reference')
        with self._locked():
            records = self._records_locked()
            target = records.get(record_id)
            if target is None:
                raise AccessDenied('not authorized')
            self._authorize(ctx, target['visibility'])
            statuses = self._effective_statuses(records)
            results = [{**r, 'effective_status': statuses[r['record_id']]}
                       for r in records.values() if r['evidence_group'] == target['evidence_group'] and
                       (ctx.audience == 'operator' or r['visibility'] == 'gm')]
            results.sort(key=lambda r: (r['saved_at_ns'], r['record_id']))
            self._authorize(ctx)
            return {'version': 1, 'results': results, 'promoted': False}
