"""Versioned shared read contract. No production wiring and no semantic pretense."""
from __future__ import annotations

import re
from typing import Protocol

from .policy import AccessContext, AccessDenied, Registry, StaleReference


class NativeReader(Protocol):
    """Adapter must bind real host authority and enforce it before returning snippets."""
    def search(self, query: str, ctx: AccessContext, limit: int) -> dict: ...


class SpecialistReader(Protocol):
    """Trusted public-SR3 adapters; never an implicit fallback to campaign data."""
    def run(self, domain: str, query: str, ctx: AccessContext, limit: int = 3) -> dict: ...


class MemoryService:
    def __init__(self, registry: Registry, native: NativeReader | None = None,
                 specialists: SpecialistReader | None = None, captures=None):
        self.registry, self.native = registry, native
        self.specialists = specialists
        self.captures = captures

    @staticmethod
    def _envelope(results: list, backends: list, **fields):
        return {'version': 1, 'results': results, 'backends': backends,
                'coverage': 'partial' if any(b['status'] != 'ready' for b in backends) else 'complete',
                **fields}

    def search(self, query: str, ctx: AccessContext, limit: int = 8,
               domain: str | None = None, mode: str = 'lexical') -> dict:
        ctx.check()
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError('query must contain 1..4000 characters')
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError('limit must be 1..30')
        if mode not in {'lexical', 'hybrid', 'specialist'}:
            raise ValueError('unsupported search mode')
        if domain == 'captured':
            if mode != 'lexical':
                raise ValueError('captured facts use their explicit private lexical reader')
            if self.captures is None:
                return self._envelope([], [{'id':'captured-files','status':'unavailable',
                    'reason':'private capture store not configured'}],status='unavailable',domain=domain)
            result = self.captures.search(query,ctx,limit=limit)
            ctx.check()
            return self._envelope([self._capture_evidence(r) for r in result['results']],
                [{'id':'captured-files','status':'ready'}],status=result['status'],domain=domain,
                mode='lexical',promoted=False,query=query)
        if domain in {'rules', 'equipment'}:
            if mode == 'hybrid':
                raise ValueError('specialist domains do not use hybrid ranking')
            if self.specialists is None:
                return self._envelope([], [{'id': domain + '-specialist', 'status': 'unavailable',
                       'reason': 'trusted specialist adapter not configured'}],
                       status='unavailable', query=query, mode='specialist', domain=domain)
            result = self.specialists.run(domain, query, ctx, limit)
            ctx.check()
            return result
        if mode == 'specialist':
            raise ValueError('specialist mode requires an explicit specialist domain')
        if mode == 'hybrid':
            if self.native is None:
                return self._envelope([], [{'id': 'openclaw', 'status': 'unavailable',
                      'reason': 'caller-bound native adapter not configured'}], query=query, mode=mode)
            result = self.native.search(query, ctx, limit)
            ctx.check()
            return result
        # Explicit lexical baseline over authorized documents ONLY. Not a replacement
        # hybrid engine. Useful to test policy/contract independently of native wiring.
        terms = set(re.findall(r'\w+', query.lower()))
        ranked = []
        for doc in self.registry.documents(ctx, domain):
            matches = list(re.finditer(r'\w+', doc.content.lower()))
            matched = [m for m in matches if m.group() in terms]
            if not matched:
                continue
            # Coverage then occurrence count. Scores are local ordering, not confidence.
            score = len({m.group() for m in matched}) / len(terms)
            idx = matched[0].start()
            start, end = max(0, idx-80), min(len(doc.content), idx+320)
            evidence = doc.evidence()
            evidence.update(excerpt=doc.content[start:end], score=score,
                            start_line=doc.section.start_line + doc.content.count('\n', 0, start),
                            end_line=min(doc.section.end_line, doc.section.start_line + doc.content.count('\n', 0, end)))
            ranked.append((score, len(matched), doc.doc_id, evidence))
        ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
        # Revalidate selected references after ranking as well: registry revocation
        # during iteration must not return a formerly allowed result.
        for item in ranked[:limit]:
            self.registry.read(item[2], ctx, item[3]['revision'])
        ctx.check()
        return self._envelope([r[3] for r in ranked[:limit]],
                             [{'id': 'authorized-lexical', 'status': 'ready'}], query=query, mode=mode,
                             coverage=self.registry.coverage)

    def get(self, doc_id: str, ctx: AccessContext, *, revision: str | None = None,
            start_line: int = 1, lines: int = 80) -> dict:
        if type(start_line) is not int or start_line < 1 or type(lines) is not int or not 1 <= lines <= 200:
            raise ValueError('invalid read bounds')
        if isinstance(doc_id,str) and doc_id.startswith('capture/'):
            if self.captures is None:
                raise AccessDenied('not authorized')
            record_id = doc_id[8:]
            history = self.captures.history(record_id,ctx)
            record = next(r for r in history['results'] if r['record_id']==record_id)
            if revision is not None and revision != record['revision']:
                raise StaleReference('source changed; search again')
            content = record['text'].splitlines()
            requested = '\n'.join(content[start_line-1:start_line-1+lines])
            text = requested[:16000]
            evidence = self._capture_evidence(record)
            evidence.pop('excerpt')  # search excerpts must not escape bounded get
            ctx.check()
            return {'version':1,'status':'ok',**evidence, 'text':text,
                    'start_line':start_line,'source_line':start_line,'lines_returned':len(text.splitlines()),
                    'truncated':len(requested)>16000 or start_line-1+lines<len(content)}
        doc = self.registry.read(doc_id, ctx, revision)
        all_lines = doc.content.splitlines()
        # Bound both line count and character count (one OCR line can be huge).
        requested = '\n'.join(all_lines[start_line-1:start_line-1+lines])
        text = requested[:16000]
        ctx.check()
        return {'version': 1, 'status': 'ok', **doc.evidence(), 'text': text,
                'start_line': start_line, 'source_line': doc.section.start_line + start_line - 1, 'lines_returned': len(text.splitlines()),
                'truncated': len(requested) > 16000 or start_line-1+lines < len(all_lines),
                'continuation': 'repeat with larger start_line; a single overlong line requires a specialist read' if len(requested)>16000 else None}

    @staticmethod
    def _capture_evidence(record):
        return {'doc_id':'capture/'+record['record_id'],'revision':record['revision'],
                'domain':'captured','visibility':record['visibility'],
                'claim_status':'provisional' if record['effective_status']=='provisional' else 'superseded',
                'record_status':record['effective_status'],'authority':'captured-provisional',
                'evidence_group':record['evidence_group'],'origin':record['origin'],
                'excerpt':record['text'][:400],'promoted':False}

    def capture(self, text, ctx: AccessContext, **request):
        ctx.check()
        if self.captures is None:
            return {'version':1,'status':'unavailable','saved':False,'searchable':False,'promoted':False}
        result = self.captures.capture(text,ctx,**request)
        ctx.check()
        return {'version':1,'status':'ok' if result['searchable'] else 'partial',**result}

    def health(self):
        return {'version': 1, 'status': 'degraded',
                'native': 'unavailable' if self.native is None else 'configured-not-probed',
                'specialists': 'unavailable' if self.specialists is None else 'configured-not-probed',
                'captures': 'unavailable' if self.captures is None else 'configured-not-probed',
                'live_cutover': False}
