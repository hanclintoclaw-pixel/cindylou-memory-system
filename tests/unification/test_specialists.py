from pathlib import Path
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

from unification.policy import AccessContext, AccessDenied, Registry, StaleReference
from unification.service import MemoryService
from unification.specialists import SpecialistReaders


class SpecialistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rules = self.root/'00_sources/rules_references/core/source.md'
        self.rules.parent.mkdir(parents=True)
        self.rules.write_text('SR3 stealth links to Quickness. Printed page 95.\n')
        self.bridge = types.ModuleType('test_bridge')
        self.bridge.__file__ = str(self.root/'bridge.py')
        Path(self.bridge.__file__).write_text('# fixture bridge backend\n')
        self.bridge.MEMORY_ROOT = self.root
        self.hit = types.SimpleNamespace(doc_id=self.rules.relative_to(self.root).as_posix(),
                                         score=4.5, snippet='Stealth (Quickness)',
                                         printed_page=95, marker_page=97, edition_tag='SR3',
                                         citation=lambda: 'SR3 Core p.95')
        self.answer = types.SimpleNamespace(accepted=True, reason='corroborated',
                                           hits=[self.hit], responsive_books=['Core', 'Companion'])
        self.bridge.page_answer = lambda **kwargs: self.answer
        self.equip = types.ModuleType('test_equipment')
        self.equip.__file__ = str(self.root/'equip.py')
        Path(self.equip.__file__).write_text('# fixture equipment backend\n')
        self.equip.DB_PATH = self.root/'equipment.sqlite'
        with closing(sqlite3.connect(self.equip.DB_PATH)) as connection:
            with connection:
                connection.execute('CREATE TABLE equipment(name TEXT)')
                connection.execute("INSERT INTO equipment VALUES ('Ares Predator')")
        self.equip.PDF_ROOT = self.root/'pdfs'
        self.equip.PDF_ROOT.mkdir()
        (self.equip.PDF_ROOT/'core.pdf').write_bytes(b'PDF fixture bytes')
        self.equip.PAGE_CACHE = self.root/'pages.json'
        self.equip.PAGE_CACHE.write_text(json.dumps({'fixture': ['cached text']}))
        self.equip.TEXT_LAYER_PDFS = {'sr3': ['core.pdf']}
        self.equip.TIER_ORDER = ['VERIFIED', 'SR3', 'WEAK', 'QUARANTINED']
        self.equip.FAN_ERA_CODES = {'tss'}
        self.equipment_hits = [self.equipment_hit()]
        self.equip.search = lambda query, dataset, limit: list(self.equipment_hits)
        self.equip.corroborate = lambda hit, cache: cache.update(in_memory=['not written'])
        self.equip.save_page_cache = lambda cache: self.fail('original cache writer invoked')
        self.specialists = SpecialistReaders(self.bridge, self.equip)
        self.service = MemoryService(Registry([]), specialists=self.specialists)

    @staticmethod
    def equipment_hit(tier='VERIFIED', name='Ares Predator'):
        return types.SimpleNamespace(name=name, dataset='gear', tier=tier,
                                     cite='sr3.278 -> Core.pdf p.280', fields={'Damage': '9M'},
                                     why='PDF corroborated', verified_tokens=['Damage'],
                                     missing_tokens=[], source_kind='official', book_code='sr3', page='278')

    def test_shared_rules_positive_keeps_printed_page_and_excerpt(self):
        result = self.service.search('stealth attribute', AccessContext(), domain='rules')
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['accepted'])
        hit = result['results'][0]
        self.assertEqual(hit['printed_page'], 95)
        self.assertEqual(hit['marker_page'], 97)
        self.assertEqual(hit['citation'], 'SR3 Core p.95')
        self.assertEqual(hit['excerpt'], 'Stealth (Quickness)')
        self.assertEqual(hit['revision'], hashlib.sha256(self.rules.read_bytes()).hexdigest())
        self.assertEqual(result['backends'][0]['measurement_scope'], 'full-sr3-specialist-corpus')

    def test_rules_decline_retains_not_admitted_candidate(self):
        self.answer.accepted = False
        self.answer.reason = 'only_1_responsive_book(s)'
        result = self.service.search('stealth', AccessContext(), domain='rules', mode='specialist')
        self.assertEqual(result['status'], 'decline')
        self.assertFalse(result['accepted'])
        self.assertFalse(result['results'][0]['admitted'])
        self.assertEqual(result['decline_reason'], 'only_1_responsive_book(s)')

    def test_rules_empty_is_decline_not_unavailable(self):
        self.answer.accepted = False
        self.answer.hits = []
        self.assertEqual(self.service.search('absent', AccessContext(), domain='rules')['status'], 'decline')

    def test_rules_missing_corpus_is_unavailable(self):
        self.rules.unlink()
        result = self.service.search('stealth', AccessContext(), domain='rules')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['results'], [])

    def test_equipment_admission_order_citation_and_cache_nonmutation(self):
        before = self.equip.PAGE_CACHE.read_bytes()
        self.equipment_hits[:] = [self.equipment_hit('WEAK', 'Weak alias'), self.equipment_hit(),
                                 self.equipment_hit('QUARANTINED', 'Foreign edition')]
        result = self.service.search('Predator', AccessContext(), domain='equipment', limit=1)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['results'][0]['tier'], 'VERIFIED')
        self.assertEqual(result['results'][0]['fields']['Damage'], '9M')
        self.assertEqual(result['results'][0]['cite'], 'sr3.278 -> Core.pdf p.280')
        self.assertEqual(result['results'][0]['printed_page'], '278')
        self.assertEqual(result['blocked_count'], 1)  # Truncation is not quarantine.
        self.assertTrue(result['truncated'])
        self.assertEqual(self.equip.PAGE_CACHE.read_bytes(), before)

    def test_all_quarantined_equipment_declines_without_leaking_rows(self):
        self.equipment_hits[:] = [self.equipment_hit('QUARANTINED', 'Foreign edition')]
        result = self.service.search('foreign', AccessContext(), domain='equipment')
        self.assertEqual(result['status'], 'decline')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['blocked_count'], 1)

    def test_fan_published_marker_not_silently_promoted_to_official(self):
        self.equipment_hits[0].book_code = 'tss'
        self.equipment_hits[0].tier = 'SR3'
        result = self.service.search('fan equipment', AccessContext(), domain='equipment')
        self.assertTrue(result['results'][0]['fan_published'])
        self.assertTrue(result['results'][0]['gm_permission_required'])
        self.assertEqual(result['results'][0]['tier'], 'SR3')

    def test_equipment_missing_database_is_unavailable(self):
        self.equip.DB_PATH.unlink()
        result = self.service.search('Predator', AccessContext(), domain='equipment')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['results'], [])

    def test_production_systemexit_and_errors_are_sanitized_unavailable(self):
        def missing(*args):
            raise SystemExit('/private/operator/database.sqlite')
        self.specialists.equip.search = missing
        result = self.service.search('Predator', AccessContext(), domain='equipment')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['backends'][0]['reason'], 'SystemExit')
        self.assertNotIn('/private/operator', str(result))

    def test_equipment_live_wal_is_unavailable_not_ignored(self):
        Path(str(self.equip.DB_PATH)+'-wal').write_bytes(b'pending rows')
        result = self.service.search('Predator', AccessContext(), domain='equipment')
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('controlled snapshot', result['backends'][0]['reason'])

    def test_production_sqlite_and_cache_writer_not_monkeypatched(self):
        original_connect = sqlite3.connect
        original_writer = self.equip.save_page_cache
        self.assertIs(sqlite3.connect, original_connect)
        self.assertIs(self.equip.save_page_cache, original_writer)
        with self.assertRaisesRegex(RuntimeError, 'cache writes disabled'):
            self.specialists.equip.save_page_cache({})
        connection = self.specialists.equip.sqlite3.connect(self.equip.DB_PATH)
        with connection:
            self.assertEqual(connection.execute('SELECT name FROM equipment').fetchone()[0], 'Ares Predator')
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO equipment VALUES ('not allowed')")
        connection.close()

    def test_cloned_search_uses_private_readonly_globals(self):
        self.equip.sqlite3 = sqlite3
        exec('def search(query, dataset, limit):\n'
             '    connection = sqlite3.connect(DB_PATH)\n'
             '    try:\n'
             '        connection.execute("CREATE TABLE forbidden(value TEXT)")\n'
             '    finally:\n'
             '        connection.close()\n', vars(self.equip))
        readers = SpecialistReaders(self.bridge, self.equip)
        result = readers.run('equipment', 'test', AccessContext())
        self.assertEqual(result['status'], 'unavailable')
        self.assertIs(self.equip.sqlite3, sqlite3)
        with closing(sqlite3.connect(self.equip.DB_PATH)) as connection:
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name='forbidden'").fetchall(), [])

    def test_context_revocation_after_io_never_releases_results(self):
        revoked = [False]
        def current():
            if revoked[0]:
                raise AccessDenied('not authorized')
        def revoke(**kwargs):
            revoked[0] = True
            return self.answer
        self.bridge.page_answer = revoke
        with self.assertRaises(AccessDenied):
            self.service.search('stealth', AccessContext(assert_current=current), domain='rules')

    def test_audience_denial_precedes_source_reads(self):
        readers = SpecialistReaders(self.bridge, self.equip, allowed_audiences=('operator',))
        with patch.object(readers, '_snapshot', side_effect=AssertionError('I/O before authorization')):
            with self.assertRaises(AccessDenied):
                readers.run('rules', 'stealth', AccessContext())

    def test_source_drift_during_request_fails_closed(self):
        def change(**kwargs):
            self.rules.write_text('Changed contents with same identity\n')
            return self.answer
        self.bridge.page_answer = change
        with self.assertRaises(StaleReference):
            self.service.search('stealth', AccessContext(), domain='rules')

    def test_source_fingerprint_recomputed_not_cached(self):
        before = self.specialists.fingerprint()
        self.rules.write_text('Edited actual bytes\n')
        after = self.specialists.fingerprint()
        self.assertNotEqual(before['rules']['generation_sha256'], after['rules']['generation_sha256'])
        self.assertEqual(before['equipment'], after['equipment'])

    def test_backend_code_drift_fails_closed(self):
        Path(self.bridge.__file__).write_text('# changed loaded backend\n')
        with self.assertRaises(StaleReference):
            self.service.search('stealth', AccessContext(), domain='rules')

    def test_shared_service_missing_specialists_and_no_hybrid_fallback(self):
        service = MemoryService(Registry([]))
        self.assertEqual(service.search('stealth', AccessContext(), domain='rules')['status'], 'unavailable')
        with self.assertRaises(ValueError):
            self.service.search('stealth', AccessContext(), domain='rules', mode='hybrid')
        with self.assertRaises(ValueError):
            self.service.search('stealth', AccessContext(), domain='campaign', mode='specialist')

    def test_rules_hit_outside_public_specialist_scope_denied(self):
        secret = self.root/'secret.md'
        secret.write_text('Not a public rulebook\n')
        self.hit.doc_id = secret.name
        with self.assertRaises(AccessDenied):
            self.service.search('stealth', AccessContext(), domain='rules')


if __name__ == '__main__':
    unittest.main()
