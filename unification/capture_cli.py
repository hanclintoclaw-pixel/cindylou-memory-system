"""Explicitly local OPERATOR capture CLI. No server, audience override or live flag.

Requires an explicit private store path. Public CLI/production callers do not
inherit these rights. Captures stay private/provisional; promotion is not a verb.
"""
import argparse
import json
import os
from pathlib import Path
import sys

from .capture import CaptureStore
from .policy import AccessContext, Registry
from .service import MemoryService


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',type=Path,required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    search=sub.add_parser('search')
    search.add_argument('--q',required=True)
    search.add_argument('--limit',type=int,default=8)
    get=sub.add_parser('get')
    get.add_argument('doc_id')
    get.add_argument('--revision')
    get.add_argument('--start-line',type=int,default=1)
    get.add_argument('--lines',type=int,default=80)
    save=sub.add_parser('save')
    save.add_argument('--text-file',type=Path,help='otherwise read standard input')
    save.add_argument('--origin-file',type=Path,required=True)
    save.add_argument('--idempotency-key',required=True)
    save.add_argument('--supersedes')
    save.add_argument('--derivative-of')
    sub.add_parser('recover')
    args=parser.parse_args()
    os.umask(0o077)
    store=CaptureStore(args.store)
    service=MemoryService(Registry([]),captures=store)
    ctx=AccessContext('operator')  # trusted local entrypoint only, not HTTP/tool JSON
    if args.command=='search':
        result=service.search(args.q,ctx,domain='captured',limit=args.limit)
    elif args.command=='get':
        result=service.get(args.doc_id,ctx,revision=args.revision,start_line=args.start_line,lines=args.lines)
    elif args.command=='save':
        text=args.text_file.read_text() if args.text_file else sys.stdin.read()
        result=service.capture(text,ctx,idempotency_key=args.idempotency_key,
            origin=json.loads(args.origin_file.read_bytes()),supersedes=args.supersedes,
            derivative_of=args.derivative_of)
    else:
        result=store.recover()
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
