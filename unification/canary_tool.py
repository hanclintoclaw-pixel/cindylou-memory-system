"""Default-off public API tool client; not registered with any production host.

Tool arguments carry operations, never transport configuration or authority.
Only trusted local construction selects a loopback port and owner-only token file.
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
from pathlib import Path
import re
import socket
import sys
import threading
import time

from .canary_api import MAX_BODY, read_token

MAX_RESPONSE = 1024 * 1024
TOOL_PARAMETERS = {
    'type': 'object', 'additionalProperties': False,
    'required': ['operation'],
    'properties': {
        'operation': {'type': 'string', 'enum': ['health', 'search', 'get']},
        'query': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 30},
        'doc_id': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
        'revision': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'start_line': {'type': 'integer', 'minimum': 1},
        'lines': {'type': 'integer', 'minimum': 1, 'maximum': 200},
    },
}


def _result(payload):
    return {'content': [{'type': 'text', 'text': json.dumps(payload, allow_nan=False)}],
            'details': payload, 'isError': payload.get('status') not in {'ok', 'empty'}}


def _failure(status):
    return _result({'version': 1, 'status': status, 'coverage': 'partial', 'results': [],
                    'caller': {'id': 'isolated-public-tool-canary', 'audience': 'public',
                               'domain': 'campaign', 'production_integration': False}})


def _request(request):
    if type(request) is not dict:
        raise ValueError('object required')
    operation = request.get('operation')
    if operation == 'health':
        allowed = {'operation'}
    elif operation == 'search':
        allowed = {'operation', 'query', 'limit'}
        query, limit = request.get('query'), request.get('limit', 8)
        if type(query) is not str or not query.strip() or len(query) > 4000 or type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError('invalid search')
    elif operation == 'get':
        allowed = {'operation', 'doc_id', 'revision', 'start_line', 'lines'}
        doc_id, revision = request.get('doc_id'), request.get('revision')
        start, lines = request.get('start_line', 1), request.get('lines', 80)
        if type(doc_id) is not str or not 1 <= len(doc_id) <= 4000 or type(revision) is not str or not re.fullmatch(r'[0-9a-f]{64}', revision):
            raise ValueError('revision-bound reference required')
        if type(start) is not int or start < 1 or type(lines) is not int or not 1 <= lines <= 200:
            raise ValueError('invalid read bounds')
    else:
        raise ValueError('unknown operation')
    if set(request) - allowed:
        raise ValueError('unknown fields')
    body = json.dumps({k: v for k, v in request.items() if k != 'operation'}, allow_nan=False).encode()
    if len(body) > MAX_BODY:
        raise ValueError('request too large')
    return operation, None if operation == 'health' else body


def _validate(payload, operation, request):
    if type(payload) is not dict or payload.get('version') != 1 or payload.get('status') not in {'ok', 'empty'}:
        raise ValueError('invalid response')
    evidence_keys = {'doc_id', 'revision', 'visibility', 'domain', 'claim_status', 'authority',
                     'evidence_group', 'section_id', 'source_start_line', 'source_end_line',
                     'citation', 'reference'}
    allowed = {'version', 'status', 'results', 'backends', 'coverage', 'caller'}
    allowed |= {'health'} if operation == 'health' else {'query', 'mode', 'dropped_outside_partition'} if operation == 'search' else evidence_keys | {'text', 'start_line', 'source_line', 'lines_returned', 'truncated'}
    if set(payload) - allowed:
        raise ValueError('unexpected response fields')
    caller = payload.get('caller', {})
    if caller.get('id') != 'isolated-public-api-canary' or caller.get('audience') != 'public' or caller.get('domain') != 'campaign' or caller.get('production_integration') is not False:
        raise ValueError('wrong caller contract')
    backends, results = payload.get('backends'), payload.get('results')
    if type(results) is not list or type(backends) is not list or not backends or any(type(b) is not dict or b.get('status') != 'ready' for b in backends):
        raise ValueError('backend not ready')
    if payload.get('warning') or payload.get('warnings') or payload.get('stale') or payload.get('disabled'):
        raise ValueError('backend warning')
    if operation != 'search' and results:
        raise ValueError('unexpected evidence outside search')
    if operation == 'search' and (len(results) > request.get('limit', 8) or (payload['status'] == 'empty') != (not results)):
        raise ValueError('invalid search result count')
    evidence = results if operation == 'search' else [payload] if operation == 'get' else []
    for hit in evidence:
        if type(hit) is not dict or hit.get('visibility') != 'public' or hit.get('domain') != 'campaign':
            raise ValueError('nonpublic evidence')
        if operation == 'search' and set(hit) - evidence_keys - {'score', 'excerpt'}:
            raise ValueError('unexpected evidence fields')
        if type(hit.get('revision')) is not str or not re.fullmatch(r'[0-9a-f]{64}', hit['revision']):
            raise ValueError('missing revision')
        if hit.get('claim_status') not in {'confirmed', 'provisional', 'disputed', 'superseded'} or not hit.get('authority') or not hit.get('evidence_group'):
            raise ValueError('missing provenance')
        citation = hit.get('citation', {})
        if type(hit.get('doc_id')) is not str or not hit['doc_id'].startswith('wiki/') or citation.get('revision') != hit['revision'] or citation.get('doc_id') != hit['doc_id']:
            raise ValueError('missing citation')
    if operation == 'get':
        if payload.get('status') != 'ok' or payload.get('doc_id') != request['doc_id'] or payload.get('revision') != request['revision']:
            raise ValueError('read reference changed')
        text = payload.get('text')
        if type(text) is not str or len(text) > 16000 or len(text.splitlines()) > request.get('lines', 80) or payload.get('start_line') != request.get('start_line', 1) or 'excerpt' in payload:
            raise ValueError('unbounded read')
        if type(payload.get('source_line')) is not int or payload['source_line'] < 1 or type(payload.get('lines_returned')) is not int or not 0 <= payload['lines_returned'] <= request.get('lines', 80) or type(payload.get('truncated')) is not bool:
            raise ValueError('missing bounded read metadata')
    # The canary never establishes full-corpus coverage, even if a backend says so.
    payload['coverage'] = 'partial'
    return payload


def execute_tool(request, *, token_file, enable_canary=False, port=18091, timeout=12.0):
    """One bounded HTTP exchange, no redirects/proxies/retry/fallback/source reads.

    The deadline bounds network connect, headers and body together. Local token
    validation is outside that network budget; no token or exception text is emitted.
    """
    if not enable_canary:
        return _failure('disabled')
    try:
        operation, body = _request(request)
        if type(port) is not int or not 1024 <= port <= 65535 or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError('invalid local configuration')
    except (ValueError, TypeError):
        return _failure('invalid_request')
    connection = timer = None
    try:
        token = read_token(token_file)
        deadline = time.monotonic() + timeout
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
        connection.connect()
        sock = connection.sock

        def expire():
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        connection.request('GET' if operation == 'health' else 'POST', '/v1/' + operation,
                           body=body, headers={'Authorization': 'Bearer ' + token,
                                              'Content-Type': 'application/json'})
        response = connection.getresponse()
        # Never follow redirects or relay remote error bodies/exception strings.
        if response.status != 200:
            return _failure({401: 'denied', 403: 'denied', 409: 'stale',
                             400: 'invalid_request', 413: 'invalid_request'}.get(response.status, 'unavailable'))
        lengths = response.headers.get_all('Content-Length') or []
        if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,9}', lengths[0]) or not 0 < int(lengths[0]) <= MAX_RESPONSE or response.getheader('Transfer-Encoding'):
            raise ValueError('invalid response length')
        if response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            raise ValueError('invalid response type')
        raw = response.read(int(lengths[0]) + 1)
        if len(raw) != int(lengths[0]) or time.monotonic() >= deadline:
            raise ValueError('incomplete or expired response')
        payload = json.loads(raw, parse_constant=lambda unused: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        return _result(_validate(payload, operation, request))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, http.client.HTTPException, RecursionError):
        return _failure('unavailable')
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if connection is not None:
            connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--enable-canary', action='store_true')
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18091)
    parser.add_argument('--timeout', type=float, default=12)
    args = parser.parse_args(argv)
    if not args.enable_canary:
        # Before stdin, token or socket I/O.
        result = _failure('disabled')
    else:
        raw = sys.stdin.buffer.read(MAX_BODY + 1)
        try:
            if len(raw) > MAX_BODY:
                raise ValueError('input too large')
            request = json.loads(raw)
            result = execute_tool(request, token_file=args.token_file, enable_canary=True,
                                  port=args.port, timeout=args.timeout)
        except (ValueError, RecursionError):
            result = _failure('invalid_request')
    print(json.dumps(result, allow_nan=False))
    return {'disabled': 2, 'invalid_request': 2, 'denied': 3, 'stale': 4,
            'unavailable': 5}.get(result['details']['status'], 0)


if __name__ == '__main__':
    raise SystemExit(main())
