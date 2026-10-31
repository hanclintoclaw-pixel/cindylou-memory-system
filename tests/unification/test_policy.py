from pathlib import Path
import tempfile
import unittest

from unification.policy import AccessContext, AccessDenied, Registry, Source, StaleReference
from unification.service import MemoryService


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        docs = {'public': 'Shared knowbot lives in Nashville.\nSecond line.',
                'gm': 'Hidden ambush secret: violet-otter.',
                'operator': 'Private operator token: silver-puma.',
                'conversation': 'Group-A-only: copper-badger.'}
        sources = []
        for visibility, text in docs.items():
            folder = self.root / visibility
            folder.mkdir()
            (folder/'note.md').write_text(text)
            sources.append(Source(visibility, folder, visibility=visibility,
                                  approved=frozenset({'note.md'}),
                                  conversation_id='A' if visibility == 'conversation' else None))
        self.registry = Registry(sources)
        self.service = MemoryService(self.registry)
        self.public = AccessContext()

    def test_public_search_never_includes_private_snippets(self):
        for secret in ['violet-otter', 'silver-puma', 'copper-badger']:
            result = self.service.search(secret, self.public)
            self.assertEqual(result['results'], [])
            self.assertNotIn(secret, str(result).replace(secret, '', 1))

    def test_denied_files_are_not_even_read(self):
        (self.root/'gm/note.md').write_bytes(b'\xff\xff')
        self.assertEqual(len(self.service.search('Nashville', self.public)['results']), 1)

    def test_public_direct_get_denied(self):
        for ns in ['gm', 'operator', 'conversation', 'unknown']:
            with self.assertRaisesRegex(AccessDenied, '^not authorized$'):
                self.service.get(ns+'/note.md', self.public)

    def test_public_reads_approved_document(self):
        hit = self.service.search('Nashville', self.public)['results'][0]
        got = self.service.get(hit['doc_id'], self.public, revision=hit['revision'])
        self.assertIn('Nashville', got['text'])
        self.assertEqual(hit['citation'], got['citation'])
        self.assertEqual(got['visibility'], 'public')

    def test_gm_cannot_get_operator_memory(self):
        ctx = AccessContext('gm')
        self.assertIn('ambush', self.service.get('gm/note.md', ctx)['text'])
        with self.assertRaises(AccessDenied):
            self.service.get('operator/note.md', ctx)

    def test_operator_is_explicit_and_local_only(self):
        got = self.service.get('operator/note.md', AccessContext('operator'))
        self.assertIn('silver-puma', got['text'])

    def test_conversation_binding(self):
        for ctx in [self.public, AccessContext('conversation'), AccessContext('conversation', 'B')]:
            with self.assertRaises(AccessDenied):
                self.service.get('conversation/note.md', ctx)
        got = self.service.get('conversation/note.md', AccessContext('conversation','A'))
        self.assertIn('copper-badger', got['text'])

    def test_unknown_audience_denied(self):
        with self.assertRaises(AccessDenied):
            self.service.search('Nashville', AccessContext('anything'))

    def test_empty_approval_admits_nothing(self):
        service = MemoryService(Registry([Source('unreviewed',self.root/'public',visibility='public')]))
        self.assertEqual(service.search('Nashville',self.public)['results'], [])
        with self.assertRaises(AccessDenied):
            service.get('unreviewed/note.md',self.public)

    def test_no_basename_fallback(self):
        with self.assertRaises(AccessDenied):
            self.service.get('note.md', self.public)

    def test_traversal_and_aliases_denied(self):
        for doc_id in ['public/../operator/note.md','public/./note.md','/public/note.md',
                       'public//note.md','public/.archive/note.md','public\\note.md',
                       'public/%2e%2e/note.md','public/note.md\x00']:
            with self.subTest(doc_id=doc_id), self.assertRaises(AccessDenied):
                self.service.get(doc_id,self.public)

    def test_symlink_file_denied(self):
        path = self.root/'public/note.md'
        path.unlink(); path.symlink_to(self.root/'operator/note.md')
        with self.assertRaises(AccessDenied):
            self.service.get('public/note.md',self.public)

    def test_symlink_directory_denied(self):
        (self.root/'public/nested').symlink_to(self.root/'operator',target_is_directory=True)
        source = Source('link',self.root/'public',visibility='public',approved=frozenset({'nested/note.md'}))
        with self.assertRaises(AccessDenied):
            MemoryService(Registry([source])).get('link/nested/note.md',self.public)

    def test_revision_change_fails_instead_of_serving_new_claim(self):
        hit = self.service.search('Nashville',self.public)['results'][0]
        (self.root/'public/note.md').write_text('Now disputed.')
        with self.assertRaises(StaleReference):
            self.service.get(hit['doc_id'],self.public,revision=hit['revision'])

    def test_revoked_context(self):
        def revoked():
            raise AccessDenied('revoked')
        with self.assertRaises(AccessDenied):
            self.service.search('Nashville', AccessContext(assert_current=revoked))

    def test_revocation_after_read(self):
        calls = []
        def revoke_after_io():
            calls.append(True)
            if len(calls) >= 5:
                raise AccessDenied('revoked')
        with self.assertRaises(AccessDenied):
            self.service.get('public/note.md', AccessContext(assert_current=revoke_after_io))

    def test_bounded_read(self):
        got = self.service.get('public/note.md',self.public,lines=1)
        self.assertTrue(got['truncated'])
        self.assertNotIn('Second line',got['text'])

    def test_bounded_long_line(self):
        (self.root/'public/note.md').write_text('x'*20000)
        got = self.service.get('public/note.md',self.public)
        self.assertEqual(len(got['text']),16000)
        self.assertTrue(got['truncated'])

    def test_invalid_bounds_and_query(self):
        for bounds in [{'lines':0},{'start_line':0},{'lines':201},{'lines':True}]:
            with self.assertRaises(ValueError):
                self.service.get('public/note.md',self.public,**bounds)
        for args in [('',{}), ('x'*4001,{}), ('x',{'limit':0}), ('x',{'mode':'semantic'})]:
            with self.assertRaises(ValueError):
                self.service.search(args[0],self.public,**args[1])

    def test_hybrid_is_unavailable_not_lexical_in_disguise(self):
        result = self.service.search('Nashville',self.public,mode='hybrid')
        self.assertEqual(result['results'],[])
        self.assertEqual(result['coverage'],'partial')
        self.assertEqual(result['backends'][0]['status'],'unavailable')

    def test_duplicate_namespaces_rejected(self):
        source = Source('test',self.root)
        with self.assertRaises(ValueError):
            Registry([source, source])


if __name__ == '__main__':
    unittest.main()
