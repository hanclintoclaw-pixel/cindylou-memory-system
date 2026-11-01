"""Isolated, default-off loopback API candidate; not an existing API replacement.

Fixed public campaign inputs, bearer authentication, read-only endpoints, no
browser/CORS authority and no sessions/capture/administrative verbs. Foreground
only; this module never installs a service or configures another caller.
"""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import stat

from .canary_cli import execute
from .native_client import validate_generation
from .policy import AccessContext

MAX_BODY = 8192


def read_token(path):
    # A route credential, not a private-record grant. Never print it or log headers.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        # The data volume may add owner-execute even after chmod(0600).
        # Enforce the actual boundary: owner-readable, no group/world access.
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or not info.st_mode & stat.S_IRUSR:
            raise ValueError('owner-only regular token file required')
        token = source.read(257).strip()
    if not re.fullmatch(rb'[A-Za-z0-9_-]{32,128}', token):
        raise ValueError('invalid local route token')
    return token.decode('ascii')


def make_server(registry, partition, token, port, *, executor=execute):
    """Trusted local construction; port=0 is for ephemeral isolated verification."""
    registry, partition = Path(registry), Path(partition)

    class Handler(BaseHTTPRequestHandler):
        # Single foreground server serializes native access. Socket reads have a
        # finite idle timeout; native exchange limits are not a total HTTP deadline.
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *unused):
            pass

        def reply(self, code, payload):
            raw = json.dumps(payload, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            # No browser access is approved at this stage, including localhost.
            if self.headers.get_all('Origin') or self.headers.get_all('Sec-Fetch-Site'):
                self.reply(403, {'status':'denied'})
                return False
            values = self.headers.get_all('Authorization') or []
            if len(values) != 1 or not hmac.compare_digest(values[0].encode(), ('Bearer '+token).encode()):
                self.reply(401, {'status':'denied'})
                return False
            return True

        def dispatch(self, command, body):
            args = argparse.Namespace(enable_canary=True,registry=registry,partition=partition,
                timeout=5.0,min_score=0.0,command=command)
            if command == 'search':
                if set(body)-{'query','limit'} or type(body.get('query')) is not str or type(body.get('limit',8)) is not int:
                    raise ValueError('invalid request')
                args.q, args.limit = body['query'],body.get('limit',8)
            elif command == 'get':
                if set(body)-{'doc_id','revision','start_line','lines'} or type(body.get('doc_id')) is not str or not 1 <= len(body['doc_id']) <= 4000:
                    raise ValueError('invalid request')
                if type(body.get('revision')) is not str or type(body.get('start_line',1)) is not int or type(body.get('lines',80)) is not int:
                    raise ValueError('invalid request')
                args.doc_id,args.revision = body['doc_id'],body['revision']
                args.start_line,args.lines = body.get('start_line',1),body.get('lines',80)
            result = executor(args)
            result['caller'] = {'id':'isolated-public-api-canary','audience':'public',
                'domain':'campaign','production_integration':False}
            code = {'denied':403,'stale':409,'unavailable':503}.get(result.get('status'),200)
            self.reply(code,result)

        def do_GET(self):
            if not self.authorized():
                return
            if self.path != '/v1/health':
                return self.reply(404,{'status':'not_found'})
            self.handle_command('health',{})

        def handle_command(self, command, body):
            try:
                self.dispatch(command,body)
            except ValueError:
                self.reply(400,{'status':'invalid_request'})
            except Exception:
                self.reply(503,{'status':'unavailable'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path not in {'/v1/search','/v1/get'}:
                return self.reply(404,{'status':'not_found'})
            lengths = self.headers.get_all('Content-Length') or []
            if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,8}',lengths[0]):
                return self.reply(400,{'status':'invalid_request'})
            size = int(lengths[0])
            if size > MAX_BODY:
                return self.reply(413,{'status':'invalid_request'})
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                return self.reply(415,{'status':'invalid_request'})
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError('incomplete body')
                body = json.loads(raw)
                if type(body) is not dict:
                    raise ValueError('invalid request')
            except (ValueError,UnicodeError,OSError):
                return self.reply(400,{'status':'invalid_request'})
            self.handle_command(self.path.rsplit('/',1)[-1],body)

    class Server(HTTPServer):
        request_queue_size = 4

    return Server(('127.0.0.1',port),Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    ap.add_argument('--enable-canary', action='store_true')
    ap.add_argument('--registry',type=Path,required=True)
    ap.add_argument('--partition',type=Path,required=True)
    ap.add_argument('--token-file',type=Path,required=True)
    ap.add_argument('--port',type=int,required=True)
    args = ap.parse_args(argv)
    if not args.enable_canary:
        ap.error('canary disabled; explicit --enable-canary required')
    if not 1024 <= args.port <= 65535:
        ap.error('explicit unprivileged loopback port required')
    try:
        token = read_token(args.token_file)
        manifest = json.loads((args.partition/'partition.json').read_text())
        registry = validate_generation(args.registry,args.partition,manifest)
        if any(doc.source.domain != 'campaign' for doc in registry.documents(AccessContext())):
            raise ValueError('campaign-only inputs required')
        with make_server(args.registry,args.partition,token,args.port) as server:
            print('Public campaign canary listening on loopback; foreground only.',flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except (OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'status':'unavailable','reason':'local canary configuration unavailable'}))
        return 5
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
