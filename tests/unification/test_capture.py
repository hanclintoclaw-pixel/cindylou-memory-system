"""Isolated durable-capture tests. Every write is below a temporary directory."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from unification.capture import CaptureConflict, CaptureIntegrityError, CaptureStore
from unification.capture import _sha
from unification.policy import AccessContext, AccessDenied


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'capture'
        self.store = CaptureStore(self.root)
        self.operator = AccessContext('operator')
        self.gm = AccessContext('gm')
        self.origin = {'doc_id': 'legacy-chat-facts/row-1',
                       'revision': hashlib.sha256(b'original source bytes').hexdigest(),
                       'record_id': 'message-123'}

    def capture(self, text='Cobalt wren lives in Nashville.', key='one', **kwargs):
        return self.store.capture(text, self.operator, idempotency_key=key,
                                  origin=self.origin, **kwargs)

    def test_private_provisional_default_and_atomic_receipt(self):
        receipt = self.capture()
        self.assertTrue(receipt['created'])
        self.assertTrue(receipt['saved'])
        self.assertTrue(receipt['searchable'])
        self.assertFalse(receipt['promoted'])
        self.assertGreaterEqual(receipt['indexed_at_ns'], receipt['saved_at_ns'])
        self.assertGreaterEqual(receipt['saved_to_searchable_ms'], 0)
        found = self.store.search('Cobalt wren', self.operator)['results']
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['origin'], self.origin)
        self.assertEqual(found[0]['visibility'], 'operator')
        self.assertEqual(found[0]['claim_status'], 'provisional')
        with closing(sqlite3.connect(self.store.index_path)) as connection:
            row = connection.execute('SELECT saved,searchable,promoted,revision FROM receipts').fetchone()
            self.assertEqual(row, (1, 1, 0, receipt['revision']))

    def test_idempotent_retry_preserves_exact_canonical_source(self):
        receipt = self.capture()
        path = self.store.records_path/(receipt['record_id']+'.json')
        raw, modified = path.read_bytes(), path.stat().st_mtime_ns
        retried = self.capture()
        self.assertFalse(retried['created'])
        self.assertEqual({k:v for k,v in retried.items() if k!='created'},
                         {k:v for k,v in receipt.items() if k!='created'})
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(path.stat().st_mtime_ns, modified)
        self.assertEqual(len(list(self.store.records_path.glob('*.json'))), 1)
        with self.assertRaises(CaptureConflict):
            self.capture(text='Changed content but reused idempotency key.')
        self.assertEqual(path.read_bytes(), raw)

    def test_searchable_latency_observation_is_after_index_commit(self):
        with patch('unification.capture.time.time_ns', side_effect=[1_000_000, 4_000_000]):
            receipt = self.capture()
        self.assertEqual(receipt['saved_at_ns'], 1_000_000)
        self.assertEqual(receipt['indexed_at_ns'], 4_000_000)
        self.assertEqual(receipt['saved_to_searchable_ms'], 3.0)

    def test_original_and_origin_survive_correction_and_chain(self):
        first = self.capture()
        path = self.store.records_path/(first['record_id']+'.json')
        original = path.read_bytes()
        second = self.capture('Cobalt wren now lives in Memphis.', key='two', supersedes=first['record_id'])
        third = self.capture('Cobalt wren now lives in Knoxville.', key='three', supersedes=second['record_id'])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.store.search('Nashville', self.operator)['results'], [])
        self.assertEqual(self.store.search('Memphis', self.operator)['results'], [])
        self.assertEqual(self.store.search('Knoxville', self.operator)['results'][0]['record_id'], third['record_id'])
        rows = self.store.history(third['record_id'], self.operator)['results']
        self.assertEqual([r['effective_status'] for r in rows], ['superseded', 'superseded', 'provisional'])
        self.assertEqual(rows[0]['origin'], self.origin)
        self.assertEqual(len({r['evidence_group'] for r in rows}), 1)
        self.assertEqual(len(self.store.search('Cobalt', self.operator, include_superseded=True)['results']), 3)

    def test_derivatives_share_evidence_group_not_independent_origins(self):
        original = self.capture()
        derivative = self.capture('Cobalt wren copied into a dossier.', key='derivative',
                                  derivative_of=original['record_id'])
        rows = self.store.history(derivative['record_id'], self.operator)['results']
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r['evidence_group'] for r in rows}), 1)
        self.assertEqual(rows[1]['derivative_of'], original['record_id'])
        self.assertTrue(all(r['effective_status'] == 'provisional' for r in rows))

    def test_competing_correction_rejected_but_idempotent_correction_retry_allowed(self):
        original = self.capture()
        correction = self.capture('Corrected fact.', key='correction', supersedes=original['record_id'])
        retry = self.capture('Corrected fact.', key='correction', supersedes=original['record_id'])
        self.assertFalse(retry['created'])
        self.assertTrue(correction['created'])
        self.assertEqual(retry['revision'],correction['revision'])
        with self.assertRaises(CaptureConflict):
            self.capture('Competing fact.', key='competing', supersedes=original['record_id'])
        self.assertEqual(len(list(self.store.records_path.glob('*.json'))), 2)

    def test_derivative_of_corrected_source_cannot_remain_current_or_outvote(self):
        original = self.capture('Original blue wren.', key='original')
        derivative = self.capture('Copied blue wren.', key='derivative', derivative_of=original['record_id'])
        second_copy = self.capture('Second copied blue wren.', key='second-copy', derivative_of=derivative['record_id'])
        correction = self.capture('Corrected red wren.', key='corrected', supersedes=original['record_id'])
        self.assertEqual(self.store.search('blue wren', self.operator)['results'], [])
        stale = self.store.search('blue wren', self.operator, include_superseded=True)['results']
        statuses = {r['record_id']:r['effective_status'] for r in stale}
        self.assertEqual(statuses[original['record_id']], 'superseded')
        self.assertEqual(statuses[derivative['record_id']], 'stale-derivative')
        self.assertEqual(statuses[second_copy['record_id']], 'stale-derivative')
        self.assertEqual(self.store.search('red wren', self.operator)['results'][0]['record_id'], correction['record_id'])
        fresh_copy = self.capture('Current red wren copied.', key='fresh-copy', derivative_of=correction['record_id'])
        self.assertEqual(len(self.store.search('red wren', self.operator)['results']), 2)
        rows = self.store.history(fresh_copy['record_id'], self.operator)['results']
        self.assertEqual(len({r['evidence_group'] for r in rows}), 1)

    def test_gm_scope_does_not_reveal_operator_records_or_history(self):
        operator = self.capture(text='Secret silver puma.')
        gm = self.store.capture('GM violet otter.', self.gm, idempotency_key='gm',
                                origin=self.origin, visibility='gm')
        self.assertEqual(self.store.search('silver puma', self.gm)['results'], [])
        self.assertEqual(self.store.search('violet otter', self.gm)['results'][0]['record_id'], gm['record_id'])
        self.assertEqual(len(self.store.search('otter', self.operator)['results']), 1)
        with self.assertRaises(AccessDenied):
            self.store.history(operator['record_id'], self.gm)
        samekey = self.store.capture('Different GM-visible fact.', self.gm, idempotency_key='one',
                                     origin=self.origin, visibility='gm')
        self.assertNotEqual(samekey['record_id'], operator['record_id'])
        self.assertEqual(self.store.search('silver puma', self.gm)['results'], [])

    def test_empty_token_captures_rejected_before_save(self):
        for text in ('!!! ???', '😀✨👍🏽', '___', '--- …'):
            with patch.object(self.store, '_persist_locked', side_effect=AssertionError('saved unsearchable text')):
                with self.assertRaisesRegex(ValueError, 'indexable'):
                    self.capture(text=text)
        self.assertEqual(self.store.recover()['saved_records'], 0)

    def test_all_tokens_exceeding_query_budget_rejected_but_short_mixed_token_reachable(self):
        for text in ('x'*5000,'x'*4001+' '+'y'*5000):
            with patch.object(self.store,'_persist_locked',side_effect=AssertionError('saved unreachable tokens')):
                with self.assertRaisesRegex(ValueError,'query budget'):
                    self.capture(text=text)
        receipt = self.capture(text='x'*5000+' cobalt',key='mixed')
        self.assertTrue(receipt['searchable'])
        self.assertEqual(self.store.search('cobalt',self.operator)['results'][0]['record_id'],receipt['record_id'])
        edge = self.capture(text='z'*4000,key='query-limit-edge')
        self.assertEqual(self.store.search('z'*4000,self.operator)['results'][0]['record_id'],edge['record_id'])

    def test_correction_requires_exact_visibility_and_hidden_derivatives_do_not_change_gm_view(self):
        original = self.store.capture('Original GM-visible blue wren.',self.gm,idempotency_key='gm-original',
                                      origin=self.origin,visibility='gm')
        gm_copy = self.store.capture('GM-visible copy blue wren.',self.gm,idempotency_key='gm-copy',
                                     origin=self.origin,visibility='gm',derivative_of=original['record_id'])
        before = self.store.history(original['record_id'],self.gm)['results']
        with self.assertRaises(AccessDenied):
            self.capture('Hidden operator-only correction.',key='hidden-correction',supersedes=original['record_id'])
        private_copy = self.capture('Private narrowed copy blue wren.',key='private-copy',
                                    derivative_of=original['record_id'])
        self.capture('Private corrected narrowed copy red wren.',key='private-copy-correction',
                     supersedes=private_copy['record_id'])
        self.assertEqual(self.store.history(original['record_id'],self.gm)['results'],before)
        self.assertEqual(len(self.store.search('blue wren',self.gm)['results']),2)
        correction = self.store.capture('Corrected GM-visible red wren.',self.operator,idempotency_key='gm-correction',
                                        origin=self.origin,visibility='gm',supersedes=original['record_id'])
        self.assertEqual(self.store.search('blue wren',self.gm)['results'],[])
        self.assertEqual(self.store.search('red wren',self.gm)['results'][0]['record_id'],correction['record_id'])
        visible = self.store.history(original['record_id'],self.gm)['results']
        self.assertEqual({r['record_id']:r['effective_status'] for r in visible},
                         {original['record_id']:'superseded',gm_copy['record_id']:'stale-derivative',
                          correction['record_id']:'provisional'})

    def test_canonical_reload_rejects_visibility_changed_correction_even_with_valid_hashes(self):
        original = self.store.capture('Original GM-visible fact.',self.gm,idempotency_key='gm-original',
                                      origin=self.origin,visibility='gm')
        correction = self.store.capture('Corrected GM-visible fact.',self.gm,idempotency_key='gm-correction',
                                        origin=self.origin,visibility='gm',supersedes=original['record_id'])
        path = self.store.records_path/(correction['record_id']+'.json')
        payload = json.loads(path.read_bytes())
        payload['visibility'] = 'operator'
        request = {k:payload[k] for k in ('text','origin','visibility','supersedes','derivative_of')}
        payload['request_sha256'] = _sha(request)
        payload['revision'] = _sha({k:v for k,v in payload.items() if k!='revision'})
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(CaptureIntegrityError,'correction visibility'):
            self.store.recover()

    def test_restricted_lineage_missing_and_inaccessible_have_same_denial(self):
        hidden = self.capture('Operator hidden original.')
        for relation in ('supersedes','derivative_of'):
            failures = []
            for target in (hidden['record_id'],'0'*64):
                with self.assertRaises(AccessDenied) as error:
                    self.store.capture('GM proposed related fact.',self.gm,idempotency_key=relation+target,
                                       origin=self.origin,visibility='gm',**{relation:target})
                failures.append((type(error.exception),str(error.exception)))
            self.assertEqual(failures[0],failures[1])

    def test_public_conversation_and_invalid_contexts_denied_before_io(self):
        for ctx in (AccessContext(), AccessContext('conversation', conversation_id='A'), AccessContext('bogus')):
            with patch.object(self.store, '_records_locked', side_effect=AssertionError('I/O before authorization')):
                with self.assertRaises(AccessDenied):
                    self.store.search('secret', ctx)
                with self.assertRaises(AccessDenied):
                    self.store.capture('Fact.', ctx, idempotency_key='x', origin=self.origin)
                with self.assertRaises(AccessDenied):
                    self.store.history('0'*64, ctx)

    def test_capture_has_no_public_promotion_input_or_visibility_widening(self):
        with self.assertRaises(AccessDenied):
            self.capture(visibility='public')
        with self.assertRaises(TypeError):
            self.capture(promoted=True)
        original = self.capture()
        for relation in ('supersedes', 'derivative_of'):
            with self.assertRaises(AccessDenied):
                self.capture(key=relation, visibility='gm', **{relation: original['record_id']})

    def test_saved_but_failed_index_receipt_then_retry_recovery(self):
        with patch.object(self.store, '_reconcile_locked', side_effect=sqlite3.OperationalError('injected index failure')):
            receipt = self.capture()
        self.assertTrue(receipt['saved'])
        self.assertTrue(receipt['created'])
        self.assertFalse(receipt['searchable'])
        self.assertFalse(receipt['promoted'])
        self.assertIsNone(receipt['indexed_at_ns'])
        self.assertEqual(len(list(self.store.records_path.glob('*.json'))), 1)
        recovered = self.capture()
        self.assertTrue(recovered['searchable'])
        self.assertFalse(recovered['created'])
        self.assertEqual(recovered['revision'], receipt['revision'])
        self.assertEqual(len(self.store.search('cobalt', self.operator)['results']), 1)

    def test_crash_after_durable_save_recovers_on_startup(self):
        program = '''
import os, sys
from pathlib import Path
from unification.capture import CaptureStore
from unification.policy import AccessContext
store=CaptureStore(Path(sys.argv[1]))
store._reconcile_locked=lambda records: os._exit(23)
store.capture('Crash retained fact.',AccessContext('operator'),idempotency_key='crash',
              origin={'doc_id':'fixture/crash','revision':'0'*64})
'''
        child = subprocess.run([sys.executable, '-c', program, str(self.root)],
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=15)
        self.assertEqual(child.returncode, 23)
        recovered = CaptureStore(self.root)
        result = recovered.search('Crash retained', self.operator)
        self.assertEqual(len(result['results']), 1)
        receipt = recovered.capture('Crash retained fact.', self.operator, idempotency_key='crash',
                                    origin={'doc_id':'fixture/crash','revision':'0'*64})
        self.assertTrue(receipt['searchable'])
        self.assertFalse(receipt['created'])
        self.assertEqual(recovered.recover()['saved_records'], 1)

    def test_bootstrap_crash_before_publication_leaves_no_final_root_and_retry_succeeds(self):
        fresh = self.root.parent/'bootstrap-crash'
        program = '''
import os,sys
from pathlib import Path
from unification.capture import CaptureStore
class CrashBeforePublication(CaptureStore):
    @staticmethod
    def _publish_bootstrap(stage,root):
        assert (stage/'inventory.json').exists()
        assert (stage/'records').is_dir()
        assert not root.exists()
        os._exit(25)
CrashBeforePublication(Path(sys.argv[1]))
'''
        child = subprocess.run([sys.executable,'-c',program,str(fresh)],
                               env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=15)
        self.assertEqual(child.returncode,25)
        self.assertFalse(fresh.exists())
        self.assertEqual(CaptureStore(fresh).recover()['saved_records'],0)
        self.assertTrue((fresh/'inventory.json').exists())

    def test_two_process_fresh_root_construction_publishes_only_ready_store(self):
        fresh = self.root.parent/'fresh-concurrent'
        program = '''
import json,sys
from pathlib import Path
from unification.capture import CaptureStore
root=Path(sys.argv[1])
store=CaptureStore(root)
print(json.dumps({'inventory':(root/'inventory.json').exists(),'saved':store.recover()['saved_records']}))
'''
        processes = [subprocess.Popen([sys.executable,'-c',program,str(fresh)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                     env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}) for _ in range(2)]
        for process in processes:
            out,err = process.communicate(timeout=20)
            self.assertEqual(process.returncode,0,err)
            self.assertEqual(json.loads(out),{'inventory':True,'saved':0})

    def test_crash_between_record_save_and_inventory_update_adopts_valid_orphan(self):
        program = '''
import os,sys
from pathlib import Path
from unification.capture import CaptureStore
from unification.policy import AccessContext
store=CaptureStore(Path(sys.argv[1]))
original=store._inventory_locked
def crash_on_new_record(records):
    if records:
        os._exit(24)
    return original(records)
store._inventory_locked=crash_on_new_record
store.capture('Record before inventory crash.',AccessContext('operator'),idempotency_key='inventory-gap',
              origin={'doc_id':'fixture/inventory-crash','revision':'0'*64})
'''
        child = subprocess.run([sys.executable,'-c',program,str(self.root)],
                               env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=15)
        self.assertEqual(child.returncode,24)
        self.assertEqual(json.loads(self.store.inventory_path.read_bytes())['records'],{})
        self.assertEqual(len(list(self.store.records_path.glob('*.json'))),1)
        recovered = CaptureStore(self.root)
        self.assertEqual(len(recovered.search('inventory crash',self.operator)['results']),1)
        self.assertEqual(len(json.loads(recovered.inventory_path.read_bytes())['records']),1)

    def test_canonical_inventory_detects_record_deletion_rename_and_whole_group_loss(self):
        first = self.capture()
        second = self.capture('Standalone red kestrel.',key='standalone')
        inventory = json.loads(self.store.inventory_path.read_bytes())
        self.assertEqual(len(inventory['records']),2)
        path = self.store.records_path/(second['record_id']+'.json')
        raw = path.read_bytes()
        moved = path.with_suffix('.moved')
        path.rename(moved)
        self.store.index_path.unlink()
        with self.assertRaisesRegex(CaptureIntegrityError,'missing or changed'):
            CaptureStore(self.root)
        moved.rename(path)
        self.assertEqual(CaptureStore(self.root).recover()['saved_records'],2)
        for source in self.store.records_path.glob('*.json'):
            source.unlink()
        self.store.index_path.unlink()
        with self.assertRaisesRegex(CaptureIntegrityError,'missing or changed'):
            CaptureStore(self.root)

    def test_missing_inventory_never_reconstructed_from_records_or_index(self):
        self.capture()
        self.store.inventory_path.unlink()
        with self.assertRaisesRegex(CaptureIntegrityError,'inventory is missing'):
            CaptureStore(self.root)
        self.store.index_path.unlink()
        with self.assertRaisesRegex(CaptureIntegrityError,'inventory is missing'):
            CaptureStore(self.root)

    def test_canonical_inventory_is_monotonic_and_rejects_rehashed_record_edits(self):
        original = self.capture()
        before = json.loads(self.store.inventory_path.read_bytes())['records']
        self.capture('Another durable assertion.',key='another')
        after = json.loads(self.store.inventory_path.read_bytes())['records']
        self.assertEqual(after[original['record_id']],before[original['record_id']])
        self.assertEqual(len(after),2)
        path = self.store.records_path/(original['record_id']+'.json')
        payload = json.loads(path.read_bytes())
        payload['text'] = 'Rehashed change must not replace saved authority.'
        payload['request_sha256'] = _sha({k:payload[k] for k in ('text','origin','visibility','supersedes','derivative_of')})
        payload['revision'] = _sha({k:v for k,v in payload.items() if k!='revision'})
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(CaptureIntegrityError,'missing or changed'):
            self.store.recover()

    def test_multi_process_concurrent_same_key_saves_once(self):
        program = '''
import json,sys
from pathlib import Path
from unification.capture import CaptureStore
from unification.policy import AccessContext
store=CaptureStore(Path(sys.argv[1]))
receipt=store.capture('Concurrent durable fact.',AccessContext('operator'),idempotency_key='same-key',
                      origin={'doc_id':'fixture/concurrency','revision':'0'*64})
print(json.dumps(receipt))
'''
        processes = [subprocess.Popen([sys.executable, '-c', program, str(self.root)],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                     env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}) for _ in range(4)]
        receipts = []
        for process in processes:
            out, err = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, err)
            receipts.append(json.loads(out))
        self.assertEqual(len({r['record_id'] for r in receipts}), 1)
        self.assertEqual(len({r['revision'] for r in receipts}), 1)
        self.assertTrue(all(r['saved'] and r['searchable'] and not r['promoted'] for r in receipts))
        self.assertEqual(sum(r['created'] for r in receipts),1)
        self.assertEqual(self.store.recover()['saved_records'], 1)

    def test_missing_index_rebuilds_from_canonical_records(self):
        receipt = self.capture()
        self.store.index_path.unlink()
        rebuilt = CaptureStore(self.root)
        found = rebuilt.search('Cobalt', self.operator)['results']
        self.assertEqual(found[0]['revision'], receipt['revision'])
        self.assertEqual(len(found), 1)

    def test_corrupt_and_incompatible_indexes_quarantined_and_rebuilt(self):
        receipt = self.capture()
        self.store.index_path.write_bytes(b'not a sqlite database')
        rebuilt = CaptureStore(self.root)
        self.assertEqual(rebuilt.search('Cobalt', self.operator)['results'][0]['revision'], receipt['revision'])
        self.assertTrue(list(self.root.glob('index.sqlite.corrupt.*')))
        with closing(sqlite3.connect(self.store.index_path)) as connection:
            connection.execute('DROP TABLE records')
            connection.execute('CREATE TABLE records(wrong TEXT)')
            connection.commit()
        rebuilt = CaptureStore(self.root)
        self.assertEqual(len(rebuilt.search('Cobalt', self.operator)['results']), 1)

    def test_index_and_receipts_transaction_rolls_back_together(self):
        original = self.capture()
        with closing(sqlite3.connect(self.store.index_path)) as connection:
            connection.execute("CREATE TRIGGER receipt_failure BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT, 'injected'); END")
            connection.commit()
        failed = self.capture('New red kestrel fact.', key='second')
        self.assertTrue(failed['saved'])
        self.assertFalse(failed['searchable'])
        with closing(sqlite3.connect(self.store.index_path)) as connection:
            self.assertEqual(connection.execute('SELECT record_id FROM records').fetchall(), [(original['record_id'],)])
            self.assertEqual(connection.execute('SELECT record_id FROM receipts').fetchall(), [(original['record_id'],)])
            connection.execute('DROP TRIGGER receipt_failure')
            connection.commit()
        self.assertEqual(self.store.recover()['saved_records'], 2)
        self.assertEqual(len(self.store.search('red kestrel', self.operator)['results']), 1)

    def test_canonical_tampering_fails_closed_not_silently_reindexed(self):
        receipt = self.capture()
        path = self.store.records_path/(receipt['record_id']+'.json')
        payload = json.loads(path.read_bytes())
        payload['text'] = 'Tampered text.'
        path.write_text(json.dumps(payload))
        with self.assertRaises(CaptureIntegrityError):
            self.store.recover()
        with self.assertRaises(CaptureIntegrityError):
            self.store.search('Cobalt', self.operator)

    def test_missing_lineage_and_invalid_origin_rejected_before_save(self):
        with self.assertRaises(CaptureConflict):
            self.capture(supersedes='0'*64)
        for origin in ({}, {'doc_id':'source','revision':'not a SHA256'},
                       {**self.origin,'start_line':1}, {**self.origin,'start_line':0,'end_line':2},
                       {**self.origin,'visibility':'public'}):
            with self.assertRaises(ValueError):
                self.store.capture('Fact.',self.operator,idempotency_key='bad',origin=origin)
        self.assertEqual(list(self.store.records_path.glob('*.json')), [])

    def test_private_permissions_and_no_symlink_controls(self):
        receipt = self.capture()
        for path in (self.root, self.store.records_path, self.store.index_path,
                     self.store.lock_path,self.store.inventory_path,self.store.records_path/(receipt['record_id']+'.json')):
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        alternative = self.root.parent/'linked'
        alternative.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            CaptureStore(alternative)

    def test_query_bounds_and_context_revocation_do_not_release_results(self):
        self.capture()
        for kwargs in ({'limit':0}, {'limit':True}, {'include_superseded':'yes'}):
            with self.assertRaises(ValueError):
                self.store.search('Cobalt',self.operator,**kwargs)
        checks = [0]
        def current():
            checks[0] += 1
            if checks[0] >= 2:
                raise AccessDenied('not authorized')
        with self.assertRaises(AccessDenied):
            self.store.search('Cobalt', AccessContext('operator', assert_current=current))


if __name__ == '__main__':
    unittest.main()
