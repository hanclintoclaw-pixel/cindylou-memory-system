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
class Section:
    """Explicit reviewed line range in one exact file revision (inclusive, 1-based)."""
    section_id: str
    start_line: int
    end_line: int
    visibility: str = 'operator'
    status: str = 'provisional'
    authority: str = 'evidence'
    evidence_group: str | None = None
    conversation_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.section_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', self.section_id):
            raise ValueError('invalid section ID')
        if type(self.start_line) is not int or type(self.end_line) is not int or not 1 <= self.start_line <= self.end_line:
            raise ValueError('invalid section bounds')
        if self.visibility not in VISIBILITIES or self.status not in STATUSES:
            raise ValueError('invalid section classification')
        if self.visibility == 'conversation' and not self.conversation_id:
            raise ValueError('conversation sections need a binding')
        if not isinstance(self.authority, str) or not self.authority:
            raise ValueError('explicit authority required')


@dataclass(frozen=True)
class Approval:
    path: str
    revision: str
    sections: tuple[Section, ...]

    def __post_init__(self):
        if not isinstance(self.path, str) or any(not p or p.startswith('.') or p in {'.', '..'} for p in self.path.split('/')) or any(c in self.path for c in ('\\', '#', '%', '\x00')) or PurePosixPath(self.path).suffix != '.md':
            raise ValueError('invalid approved path')
        if not isinstance(self.revision, str) or not re.fullmatch(r'[0-9a-f]{64}', self.revision):
            raise ValueError('SHA-256 approval revision required')
        if not isinstance(self.sections, tuple) or not self.sections or not all(isinstance(s, Section) for s in self.sections):
            raise ValueError('explicit immutable sections required')
        if len({s.section_id for s in self.sections}) != len(self.sections):
            raise ValueError('duplicate section ID')
        ordered = sorted(self.sections, key=lambda s: s.start_line)
        if any(left.end_line >= right.start_line for left, right in zip(ordered, ordered[1:])):
            raise ValueError('overlapping approvals')


@dataclass(frozen=True)
class Source:
    namespace: str
    root: Path
    domain: str = 'operations'
    approvals: tuple[Approval, ...] = ()
    evidence_group: str | None = None

    def __post_init__(self):
        if not re.fullmatch(r'[a-z][a-z0-9_-]*', self.namespace):
            raise ValueError('invalid namespace')
        if not self.root.is_absolute():
            raise ValueError('absolute source root required')
        if not isinstance(self.approvals, tuple) or not all(isinstance(a, Approval) for a in self.approvals):
            raise ValueError('explicit immutable approvals required')
        if len({a.path for a in self.approvals}) != len(self.approvals):
            raise ValueError('duplicate approved path')


@dataclass(frozen=True)
class Document:
    doc_id: str
    revision: str
    content: str
    source: Source
    section: Section

    def evidence(self):
        file_id = self.doc_id.split('#')[0]
        return {'doc_id': self.doc_id, 'revision': self.revision,
                'visibility': self.section.visibility, 'domain': self.source.domain,
                'claim_status': self.section.status, 'authority': self.section.authority,
                'evidence_group': self.section.evidence_group or self.source.evidence_group or file_id,
                'section_id': self.section.section_id,
                'source_start_line': self.section.start_line,
                'source_end_line': self.section.end_line,
                'citation': {'doc_id': file_id, 'revision': self.revision,
                             'start_line': self.section.start_line, 'end_line': self.section.end_line}}


class Registry:
    def __init__(self, sources: list[Source], coverage: str = 'partial'):
        if coverage not in {'complete','partial'}:
            raise ValueError('invalid registry coverage')
        self.coverage = coverage
        self.sources = {s.namespace: s for s in sources}
        if len(self.sources) != len(sources):
            raise ValueError('duplicate namespace')

    @staticmethod
    def _permits(source: Section, ctx: AccessContext) -> bool:
        ctx.check()
        if source.visibility == 'public':
            return True
        if ctx.audience == 'operator':
            return True
        if source.visibility == 'gm' and ctx.audience == 'gm':
            return True
        return (source.visibility == 'conversation' and ctx.audience == 'conversation'
                and source.conversation_id == ctx.conversation_id)

    def _resolve(self, doc_id: str, ctx: AccessContext) -> tuple[Source, Path, Approval, Section]:
        ctx.check()
        if not isinstance(doc_id, str) or '\\' in doc_id or '\x00' in doc_id:
            raise AccessDenied('not authorized')
        file_id, separator, section_id = doc_id.partition('#')
        parts = file_id.split('/')
        if len(parts) < 2 or any(not p or p in {'.', '..'} or p.startswith('.') for p in parts):
            raise AccessDenied('not authorized')
        source = self.sources.get(parts[0])
        rel = '/'.join(parts[1:])
        approval = next((a for a in source.approvals if a.path == rel), None) if source else None
        if approval is None:
            raise AccessDenied('not authorized')
        # Whole-page aliases are allowed only for a single approved section. The
        # read below additionally proves it spans the complete file. Mixed pages
        # require a section reference, even for operator calls.
        section = next((s for s in approval.sections if s.section_id == section_id), None) if separator else (approval.sections[0] if len(approval.sections) == 1 else None)
        if section is None or not self._permits(section, ctx):
            raise AccessDenied('not authorized')
        if PurePosixPath(rel).suffix != '.md':
            raise AccessDenied('not authorized')
        path = source.root
        if path.is_symlink() or path.resolve() != path:
            raise AccessDenied('not authorized')
        for part in parts[1:]:
            path /= part
            if path.is_symlink():
                raise AccessDenied('not authorized')
        if not path.resolve().is_relative_to(source.root.resolve()):
            raise AccessDenied('not authorized')
        return source, path, approval, section

    def read(self, doc_id: str, ctx: AccessContext, revision: str | None = None) -> Document:
        source, path, approval, section = self._resolve(doc_id, ctx)
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
                fd = os.open(rel_parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(fd, 'rb') as f:
                    before = os.fstat(f.fileno())
                    import stat
                    if not stat.S_ISREG(before.st_mode):
                        raise AccessDenied('not authorized')
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
        if approval.revision != current:
            raise StaleReference('approved revision changed; review required')
        if revision is not None and revision != current:
            raise StaleReference('source changed; search again')
        # Recheck classification/path and invocation currency after I/O.
        if self._resolve(doc_id, ctx) != (source, path, approval, section):
            raise AccessDenied('not authorized')
        ctx.check()
        lines = raw.decode('utf-8').splitlines(keepends=True)
        if section.end_line > len(lines):
            raise ValueError('approved section exceeds source bounds')
        if '#' not in doc_id and (section.start_line != 1 or section.end_line != len(lines)):
            raise AccessDenied('not authorized')
        content = ''.join(lines[section.start_line-1:section.end_line])
        canonical_id = doc_id.split('#')[0] + '#' + section.section_id
        return Document(canonical_id, current, content, source, section)

    def documents(self, ctx: AccessContext, domain: str | None = None):
        ctx.check()
        for source in self.sources.values():
            if domain and source.domain != domain:
                continue
            for approval in source.approvals:
                for section in approval.sections:
                    if not self._permits(section, ctx):
                        continue  # Denied text never reaches scoring/snippets.
                    yield self.read(source.namespace + '/' + approval.path + '#' + section.section_id, ctx)
