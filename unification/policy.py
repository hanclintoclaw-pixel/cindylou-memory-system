"""Deny-by-default source registry and audience boundary.

This is a library, NOT an authenticated transport. Only trusted adapters construct
AccessContext; never deserialize caller-provided JSON into this type.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

VISIBILITIES = frozenset({'public', 'gm', 'operator', 'conversation'})
STATUSES = frozenset({'confirmed', 'provisional', 'disputed', 'superseded'})


class AccessDenied(PermissionError):
    """Generic denial; no forbidden document identity or existence disclosure."""


class StaleReference(ValueError):
    pass


@dataclass(frozen=True)
class AccessContext:
    # Transport-owned classification; public remains public even for an operator sender.
    audience: str = 'public'
    conversation_id: str | None = None
    assert_current: Callable[[], None] = field(default=lambda: None, repr=False, compare=False)

    def check(self):
        self.assert_current()
        if self.audience not in VISIBILITIES:
            raise AccessDenied('not authorized')


@dataclass(frozen=True)
class Source:
    namespace: str
    root: Path
    visibility: str = 'operator'
    domain: str = 'operations'
    status: str = 'provisional'
    # Explicit approved paths. An empty set admits nothing, including for operators.
    approved: frozenset[str] = frozenset()
    conversation_id: str | None = None
    authority: str = 'evidence'
    evidence_group: str | None = None

    def __post_init__(self):
        if not re.fullmatch(r'[a-z][a-z0-9_-]*', self.namespace):
            raise ValueError('invalid namespace')
        if self.visibility not in VISIBILITIES or self.status not in STATUSES:
            raise ValueError('invalid source classification')
        if self.visibility == 'conversation' and not self.conversation_id:
            raise ValueError('conversation sources need a binding')


@dataclass(frozen=True)
class Document:
    doc_id: str
    revision: str
    content: str
    source: Source

    def evidence(self):
        return {'doc_id': self.doc_id, 'revision': self.revision,
                'visibility': self.source.visibility, 'domain': self.source.domain,
                'status': self.source.status, 'authority': self.source.authority,
                'evidence_group': self.source.evidence_group or self.doc_id,
                'citation': {'doc_id': self.doc_id, 'revision': self.revision}}


class Registry:
    def __init__(self, sources: list[Source], coverage: str = 'partial'):
        if coverage not in {'complete','partial'}:
            raise ValueError('invalid registry coverage')
        self.coverage = coverage
        self.sources = {s.namespace: s for s in sources}
        if len(self.sources) != len(sources):
            raise ValueError('duplicate namespace')

    @staticmethod
    def _permits(source: Source, ctx: AccessContext) -> bool:
        ctx.check()
        if source.visibility == 'public':
            return True
        if ctx.audience == 'operator':
            return True
        if source.visibility == 'gm' and ctx.audience == 'gm':
            return True
        return (source.visibility == 'conversation' and ctx.audience == 'conversation'
                and source.conversation_id == ctx.conversation_id)

    def _resolve(self, doc_id: str, ctx: AccessContext) -> tuple[Source, Path]:
        ctx.check()
        if not isinstance(doc_id, str) or '\\' in doc_id or '\x00' in doc_id:
            raise AccessDenied('not authorized')
        parts = doc_id.split('/')
        if len(parts) < 2 or any(not p or p in {'.', '..'} or p.startswith('.') for p in parts):
            raise AccessDenied('not authorized')
        source = self.sources.get(parts[0])
        rel = '/'.join(parts[1:])
        if source is None or not self._permits(source, ctx) or rel not in source.approved:
            raise AccessDenied('not authorized')
        if PurePosixPath(rel).suffix != '.md':
            raise AccessDenied('not authorized')
        path = source.root
        if path.is_symlink():
            raise AccessDenied('not authorized')
        for part in parts[1:]:
            path /= part
            if path.is_symlink():
                raise AccessDenied('not authorized')
        if not path.resolve().is_relative_to(source.root.resolve()):
            raise AccessDenied('not authorized')
        return source, path

    def read(self, doc_id: str, ctx: AccessContext, revision: str | None = None) -> Document:
        source, path = self._resolve(doc_id, ctx)
        ctx.check()
        try:
            # O_NOFOLLOW protects the final file as well as the earlier path checks.
            import os
            # Traverse using held directory descriptors so replacing a parent with a
            # symlink between validation and open cannot escape the approved root.
            directory = os.open(source.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            rel_parts = path.relative_to(source.root).parts
            try:
                for part in rel_parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    os.close(directory)
                    directory = child
                fd = os.open(rel_parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
                with os.fdopen(fd, 'rb') as f:
                    before = os.fstat(f.fileno())
                    raw = f.read()
                    after = os.fstat(f.fileno())
                    if (before.st_mtime_ns,before.st_size) != (after.st_mtime_ns,after.st_size):
                        raise StaleReference('source changed during read; retry')
            finally:
                os.close(directory)
        except FileNotFoundError:
            raise FileNotFoundError('approved document unavailable') from None
        except OSError as e:
            import errno
            if e.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise AccessDenied('not authorized') from None
            raise
        current = hashlib.sha256(raw).hexdigest()
        if revision is not None and revision != current:
            raise StaleReference('source changed; search again')
        # Recheck classification/path and invocation currency after I/O.
        self._resolve(doc_id, ctx)
        ctx.check()
        return Document(doc_id, current, raw.decode('utf-8'), source)

    def documents(self, ctx: AccessContext, domain: str | None = None):
        ctx.check()
        for source in self.sources.values():
            if domain and source.domain != domain:
                continue
            if not self._permits(source, ctx):
                continue  # No read, score, snippet, count, or path from denied sources.
            for rel in sorted(source.approved):
                yield self.read(source.namespace + '/' + rel, ctx)
