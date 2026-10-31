"""Default-off, public-only campaign CLI canary; no existing caller is changed.

Explicit registry and partition paths are trusted local operator configuration,
not remote request parameters. No private captures, specialist fallback, server,
source approvals, index preparation or production installation are provided.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .native_client import NativeClient
from .policy import AccessContext, AccessDenied, StaleReference
from .registry import load_registry
from .service import MemoryService


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--enable-canary', action='store_true', help='explicit per-invocation opt in')
    ap.add_argument('--registry', required=True, type=Path)
    ap.add_argument('--partition', required=True, type=Path, help='existing reviewed public partition directory')
    ap.add_argument('--timeout', type=float, default=20.0, help='native exchange timeout, seconds (not total CLI deadline)')
    ap.add_argument('--min-score', type=float, default=0.0, help='candidate floor, never answer confidence')
    sub = ap.add_subparsers(dest='command', required=True)
    search = sub.add_parser('search')
    search.add_argument('--q', required=True)
    search.add_argument('--limit', type=int, default=8)
    get = sub.add_parser('get')
    get.add_argument('doc_id')
    get.add_argument('--revision', required=True, help='full-file SHA-256 from search')
    get.add_argument('--start-line', type=int, default=1, help='relative to the approved section')
    get.add_argument('--lines', type=int, default=80)
    sub.add_parser('health')
    return ap


def execute(args, *, client_factory=NativeClient):
    # Check activation/input before touching a source or creating a native child.
    if not args.enable_canary:
        raise ValueError('canary disabled; explicit --enable-canary required')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 20:
        raise ValueError('timeout must be in (0,20] seconds')
    if not math.isfinite(args.min_score) or args.min_score < 0:
        raise ValueError('finite nonnegative minimum score required')
    if args.command == 'search' and (not args.q.strip() or len(args.q) > 4000 or not 1 <= args.limit <= 30):
        raise ValueError('query must contain 1..4000 characters; limit must be 1..30')
    if args.command == 'get':
        import re
        if not re.fullmatch(r'[0-9a-f]{64}', args.revision):
            raise ValueError('full-file SHA-256 revision required')
        if args.start_line < 1 or not 1 <= args.lines <= 200:
            raise ValueError('invalid read bounds')
    try:
        registry = load_registry(args.registry)
        ctx = AccessContext()  # Sender identity never grants private output rights.
        if any(doc.source.domain != 'campaign' for doc in registry.documents(ctx)):
            raise ValueError('campaign-only canary requires campaign-only public inputs')
        with client_factory(args.registry, args.partition, timeout=args.timeout,
                            min_score=args.min_score) as native:
            service = MemoryService(registry, native=native)
            if args.command == 'search':
                result = service.search(args.q, ctx, limit=args.limit, domain='campaign', mode='hybrid')
            elif args.command == 'get':
                # The native reader revalidates the COMPLETE supplied generation
                # before and after bounded reads, including registry revocation.
                result = native.get(args.doc_id, ctx, revision=args.revision,
                                    start_line=args.start_line, lines=args.lines)
            else:
                result = native.health(ctx)
    except AccessDenied:
        result = {'version': 1, 'status': 'denied', 'results': [], 'coverage': 'partial'}
    except StaleReference:
        result = {'version': 1, 'status': 'stale', 'results': [], 'coverage': 'partial'}
    except (OSError, ValueError, KeyError, TypeError):
        # No source paths, private parser input or traceback in caller output.
        result = {'version': 1, 'status': 'unavailable', 'results': [], 'coverage': 'partial',
                  'reason': 'reviewed native generation unavailable'}
    result['caller'] = {'id': 'isolated-public-cli-canary', 'audience': 'public',
                        'domain': 'campaign', 'production_integration': False,
                        'candidate_min_score': args.min_score}
    return result


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    try:
        result = execute(args)
    except ValueError as error:
        ap.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return {'denied': 3, 'stale': 4, 'unavailable': 5}.get(result.get('status'), 0)


if __name__ == '__main__':
    raise SystemExit(main())
