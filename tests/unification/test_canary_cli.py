"""Caller boundary checks with the real native protocol and isolated fixtures."""
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from unification.canary_cli import execute, parser
from unification.native_client import NativeClient
import test_native_client as fixtures


class CanaryCliTests(unittest.TestCase):
    setUp = fixtures.NativeClientTests.setUp
    save_registry = fixtures.NativeClientTests.save_registry
    requests = fixtures.NativeClientTests.requests

    def args(self, *command, enabled=True):
        return parser().parse_args((['--enable-canary'] if enabled else []) + [
            '--registry', str(self.registry_path), '--partition', str(self.partition), *command])

    def run_caller(self, args, **fixture):
        self.fixture_path.write_text(json.dumps({'log': str(self.log), **fixture}))
        clients = []
        def factory(registry, partition, **kwargs):
            client = NativeClient(registry, partition, command=[sys.executable, str(fixtures.STUB), str(self.fixture_path)], **kwargs)
            clients.append(client)
            return client
        result = execute(args, client_factory=factory)
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0]._closed)
        if clients[0].process is not None:
            self.assertIsNotNone(clients[0].process.poll())
        return result

    def test_disabled_and_bad_input_never_open_sources(self):
        cases = [self.args('search', '--q', 'wren', enabled=False),
                 self.args('search', '--q', ' '), self.args('get', self.doc_id, '--revision', 'bad'),
                 self.args('get', self.doc_id, '--revision', self.revision, '--lines', '201')]
        for args in cases:
            with patch('unification.canary_cli.load_registry', side_effect=AssertionError('source I/O')):
                with self.assertRaises(ValueError):
                    execute(args)

    def test_shared_native_search_public_context_and_teardown(self):
        result = self.run_caller(self.args('search', '--q', 'wren'))
        self.assertEqual(result['status'], 'empty')
        self.assertEqual(result['caller']['audience'], 'public')
        self.assertFalse(result['caller']['production_integration'])
        request = next(r for r in self.requests() if r.get('verb') == 'search')
        self.assertEqual(request['minScore'], 0)
        self.assertEqual(request['query'], 'wren')

    def test_generation_revoked_before_child_launch(self):
        self.payload['sources'] = []
        self.save_registry()
        result = self.run_caller(self.args('get', self.doc_id, '--revision', self.revision))
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(self.requests(), [])

    def test_bounded_get_passes_exact_revision_and_section_offsets(self):
        result = self.run_caller(self.args('get', self.doc_id, '--revision', self.revision,
                                         '--start-line', '2', '--lines', '1'))
        request = next(r for r in self.requests() if r.get('verb') == 'get')
        self.assertEqual((request['revision'], request['from'], request['lines']), (self.revision, 2, 1))
        self.assertNotEqual(result['status'], 'unavailable')

    def test_missing_generation_sanitized_and_machine_nonzero(self):
        run = subprocess.run([sys.executable, '-m', 'unification.canary_cli', '--enable-canary',
            '--registry', str(self.root/'private-missing.json'), '--partition', str(self.partition),
            'health'], capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 5)
        result = json.loads(run.stdout)
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn(str(self.root), run.stdout + run.stderr)

    def test_no_audience_or_write_or_fallback_options(self):
        for command in (['--audience', 'operator', 'health'], ['save'], ['search', '--q', 'wren', '--mode', 'lexical']):
            with patch('sys.stderr'), self.assertRaises(SystemExit):
                self.args(*command)

    def test_backend_failure_never_falls_back_to_matching_lexical_source(self):
        result = self.run_caller(self.args('search', '--q', 'wren'), die=True)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['results'], [])

    def test_other_public_domain_refused_before_child_creation(self):
        self.payload['sources'][0]['domain'] = 'operations'
        self.save_registry()
        with patch('unification.canary_cli.NativeClient', side_effect=AssertionError('created child')):
            result = execute(self.args('health'), client_factory=lambda *a, **kw: self.fail('created child'))
        self.assertEqual(result['status'], 'unavailable')

    def test_stale_denied_unavailable_retained(self):
        for status in ('stale', 'denied', 'unavailable'):
            with self.subTest(status=status):
                result = self.run_caller(self.args('get', self.doc_id, '--revision', self.revision),
                    response={'version': 1, 'status': status, 'results': [], 'coverage': 'partial',
                              'backends': [{'id': 'openclaw', 'status': status}]})
                self.assertEqual(result['status'], status)
                self.assertEqual(result['results'], [])
