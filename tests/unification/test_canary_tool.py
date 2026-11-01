import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from unification.canary_api import make_server
from unification.canary_tool import MAX_RESPONSE, TOOL_PARAMETERS, execute_tool, main


def envelope():
    return {'version': 1, 'status': 'ok', 'results': [], 'coverage': 'partial',
            'backends': [{'id': 'openclaw', 'status': 'ready'}]}


def evidence():
    return {'doc_id': 'wiki/NPCs/Synthetic.md#public', 'revision': 'a'*64,
            'domain': 'campaign', 'visibility': 'public', 'claim_status': 'provisional',
            'authority': 'evidence', 'evidence_group': 'synthetic',
            'citation': {'doc_id': 'wiki/NPCs/Synthetic.md#public', 'revision': 'a'*64,
                         'start_line': 10, 'end_line': 12}}


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.token = Path(self.scratch.name)/'token'
        self.token.write_text('x'*43)
        self.token.chmod(0o600)
        self.payload = envelope()
        self.calls = []

        def executor(args):
            self.calls.append(args)
            return copy.deepcopy(self.payload)

        self.server = make_server('/unused', '/unused', 'x'*43, 0, executor=executor)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())

    def call(self, request, **kwargs):
        return execute_tool(request, token_file=self.token, enable_canary=True,
                            port=self.server.server_port, **kwargs)

    def test_disabled_before_token_stdin_or_network(self):
        with patch('unification.canary_tool.read_token') as token, patch('unification.canary_tool.http.client.HTTPConnection') as connection:
            self.assertEqual(execute_tool({}, token_file='/missing')['details']['status'], 'disabled')
            with patch('sys.stdin') as source, patch('builtins.print'):
                self.assertEqual(main(['--token-file', '/missing']), 2)
                source.buffer.read.assert_not_called()
            token.assert_not_called()
            connection.assert_not_called()

    def test_unknown_fields_authority_and_bad_bounds_before_io(self):
        cases = [{'operation': 'health', 'audience': 'operator'},
                 {'operation': 'search', 'query': 'x', 'endpoint': 'http://remote'},
                 {'operation': 'search', 'query': 'x', 'limit': True},
                 {'operation': 'search', 'query': ' '},
                 {'operation': 'get', 'doc_id': 'x'},
                 {'operation': 'get', 'doc_id': 'x', 'revision': 'a'*64, 'lines': 201},
                 {'operation': 'get', 'doc_id': 'x', 'revision': 'a'*64, 'start_line': True},
                 {'operation': 'capture', 'text': 'private'}, [],
                 {'operation': 'search', 'query': '\u2603'*4000}]
        with patch('unification.canary_tool.read_token') as token:
            for request in cases:
                with self.subTest(request=str(request)[:80]):
                    self.assertEqual(self.call(request)['details']['status'], 'invalid_request')
            token.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_search_preserves_evidence_and_provisional_citations(self):
        self.payload['results'] = [{**evidence(), 'excerpt': 'Synthetic fact', 'score': .3}]
        result = self.call({'operation': 'search', 'query': 'Synthetic', 'limit': 1})
        self.assertFalse(result['isError'])
        self.assertEqual(result['details']['results'], self.payload['results'])
        self.assertEqual(json.loads(result['content'][0]['text']), result['details'])
        self.assertEqual((self.calls[0].command, self.calls[0].limit), ('search', 1))

    def test_exact_bounded_get_preserves_source_coordinates(self):
        self.payload.update(**evidence(), text='one line', start_line=2, source_line=11,
                            lines_returned=1, truncated=True)
        request = {'operation': 'get', 'doc_id': evidence()['doc_id'], 'revision': 'a'*64,
                   'start_line': 2, 'lines': 1}
        result = self.call(request)
        self.assertFalse(result['isError'])
        self.assertEqual(result['details']['citation'], evidence()['citation'])
        for mutation in [{'text': 'one\ntwo'}, {'excerpt': 'OUTSIDE REQUEST'},
                         {'revision': 'b'*64}, {'start_line': 1}]:
            self.payload.update(mutation)
            self.assertEqual(self.call(request)['details']['status'], 'unavailable')
            self.payload = {**envelope(), **evidence(), 'text': 'one line', 'start_line': 2,
                            'source_line': 11, 'lines_returned': 1, 'truncated': True}

    def test_nonsearch_responses_cannot_relay_unexpected_evidence(self):
        secret = 'UNEXPECTED PRIVATE EVIDENCE'
        for operation in ['health', 'get']:
            self.payload = {**envelope(), **evidence(), 'text': 'one line', 'start_line': 1,
                            'source_line': 10, 'lines_returned': 1, 'truncated': True,
                            'results': [{'visibility': 'gm', 'excerpt': secret}]}
            request = {'operation': operation}
            if operation == 'get':
                request.update(doc_id=evidence()['doc_id'], revision='a'*64, lines=1)
            result = self.call(request)
            self.assertEqual(result['details']['status'], 'unavailable')
            self.assertNotIn(secret, json.dumps(result))

    def test_unknown_passage_fields_fail_closed(self):
        for request, payload in [({'operation': 'health'}, {**envelope(), 'text': 'PRIVATE'}),
                                 ({'operation': 'search', 'query': 'x'},
                                  {**envelope(), 'results': [{**evidence(), 'extra_passage': 'PRIVATE'}]})]:
            self.payload = payload
            result = self.call(request)
            self.assertEqual(result['details']['status'], 'unavailable')
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_health_and_empty_remain_distinct_from_unavailable(self):
        self.assertEqual(self.call({'operation': 'health'})['details']['status'], 'ok')
        self.payload['status'] = 'empty'
        result = self.call({'operation': 'search', 'query': 'absent'})
        self.assertEqual(result['details']['status'], 'empty')
        self.assertFalse(result['isError'])
        self.payload['backends'][0]['status'] = 'unavailable'
        self.assertEqual(self.call({'operation': 'search', 'query': 'absent'})['details']['status'], 'unavailable')

    def test_api_error_statuses_are_sanitized_and_do_not_retry(self):
        for status in ['denied', 'stale', 'unavailable']:
            self.payload = {**envelope(), 'status': status, 'secret': 'PRIVATE ERROR'}
            before = len(self.calls)
            result = self.call({'operation': 'health'})
            self.assertEqual(result['details']['status'], status)
            self.assertNotIn('PRIVATE ERROR', json.dumps(result))
            self.assertEqual(len(self.calls), before+1)

    def test_private_malformed_and_warning_responses_fail_closed(self):
        original = {**envelope(), 'results': [evidence()]}
        for key, value in [('visibility', 'operator'), ('revision', ''), ('citation', {}), ('domain', 'captured')]:
            self.payload = copy.deepcopy(original)
            self.payload['results'][0][key] = value
            self.assertEqual(self.call({'operation': 'search', 'query': 'x'})['details']['status'], 'unavailable')
        for update in [{'warning': 'stale'}, {'disabled': True}, {'backends': []}, {'results': 'bad'}]:
            self.payload = {**original, **update}
            self.assertEqual(self.call({'operation': 'search', 'query': 'x'})['details']['status'], 'unavailable')

    def test_bad_credentials_and_closed_port_do_not_leak(self):
        self.token.write_text('y'*43)
        self.assertEqual(self.call({'operation': 'health'})['details']['status'], 'denied')
        self.token.chmod(0o644)
        result = self.call({'operation': 'health'})
        self.assertEqual(result['details']['status'], 'unavailable')
        self.assertNotIn(str(self.token), json.dumps(result))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.token.chmod(0o600)
        result = execute_tool({'operation': 'health'}, token_file=self.token,
                              enable_canary=True, port=port, timeout=.2)
        self.assertEqual(result['details']['status'], 'unavailable')


class TransportTests(unittest.TestCase):
    def test_plugin_schema_matches_validated_client_surface(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(json.loads((root/'integrations/openclaw-memory-canary/tool-parameters.json').read_text()), TOOL_PARAMETERS)

    def exercise(self, mode):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *unused):
                pass

            def do_GET(self):
                try:
                    if mode == 'redirect':
                        self.send_response(302)
                        self.send_header('Location', 'http://example.invalid/secret')
                        self.end_headers()
                    elif mode == 'oversize':
                        self.send_response(200)
                        self.send_header('Content-Length', str(MAX_RESPONSE+1))
                        self.end_headers()
                    else:
                        if mode == 'slow_headers':
                            for byte in b'HTTP/1.0 200 OK\r\nContent-Length: 1000\r\n\r\n':
                                self.wfile.write(bytes([byte]))
                                self.wfile.flush()
                                time.sleep(.02)
                            return
                        self.send_response(200)
                        self.send_header('Content-Length', '1000')
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        if mode == 'malformed':
                            self.wfile.write(b'{broken')
                        elif mode == 'slow':
                            for unused in range(40):
                                self.wfile.write(b' ')
                                self.wfile.flush()
                                time.sleep(.02)
                except OSError:
                    pass

        with tempfile.TemporaryDirectory() as root:
            token = Path(root)/'token'
            token.write_text('z'*43)
            token.chmod(0o600)
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
            thread.start()
            try:
                start = time.monotonic()
                result = execute_tool({'operation': 'health'}, token_file=token,
                                      port=server.server_port, enable_canary=True, timeout=.12)
                elapsed = time.monotonic()-start
                self.assertEqual(result['details']['status'], 'unavailable')
                self.assertLess(elapsed, .6)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

    def test_redirect_is_never_followed(self):
        self.exercise('redirect')

    def test_oversized_response_is_not_read(self):
        self.exercise('oversize')

    def test_malformed_incomplete_response_is_unavailable(self):
        self.exercise('malformed')

    def test_slow_drip_cannot_extend_absolute_deadline(self):
        self.exercise('slow')

    def test_slow_headers_cannot_extend_absolute_deadline(self):
        self.exercise('slow_headers')
