"""Public-only shadow CLI. No audience override, server, or production flag."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .policy import AccessContext, AccessDenied, StaleReference
from .registry import load_registry
from .service import MemoryService

DEFAULT_REGISTRY = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification/registry.pilot.json')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registry',type=Path,default=DEFAULT_REGISTRY,help='trusted local developer manifest')
    sub = ap.add_subparsers(dest='command',required=True)
    search = sub.add_parser('search')
    search.add_argument('--q',required=True)
    search.add_argument('--mode',choices=['lexical','hybrid'],default='lexical')
    search.add_argument('--limit',type=int,default=8)
    get = sub.add_parser('get')
    get.add_argument('doc_id')
    get.add_argument('--revision')
    get.add_argument('--start-line',type=int,default=1)
    get.add_argument('--lines',type=int,default=80)
    sub.add_parser('health')
    args = ap.parse_args()
    service = MemoryService(load_registry(args.registry))
    ctx = AccessContext()  # CLI always public. Local ownership is NOT a public-output grant.
    try:
        if args.command == 'search':
            result = service.search(args.q,ctx,limit=args.limit,mode=args.mode)
        elif args.command == 'get':
            result = service.get(args.doc_id,ctx,revision=args.revision,start_line=args.start_line,lines=args.lines)
        else:
            result = service.health()
    except AccessDenied:
        result = {'version':1,'status':'denied','error':'not authorized'}
    except StaleReference:
        result = {'version':1,'status':'stale','error':'source changed; search again'}
    except FileNotFoundError:
        result = {'version':1,'status':'unavailable','error':'approved source unavailable'}
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
