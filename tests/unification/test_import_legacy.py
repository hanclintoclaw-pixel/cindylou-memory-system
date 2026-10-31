import json
from pathlib import Path
import tempfile
import unittest

from unification.capture import CaptureStore
from unification.import_legacy import import_jsonl
from unification.policy import AccessContext, AccessDenied


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'chat.jsonl'
        self.original={'fact':'Cobalt wren has a blue hat.','confidence':1,'visibility':'public',
                       'claim_status':'confirmed','source':'unverified historical label','tags':['tag']}
        self.line=json.dumps(self.original)
        self.source.write_text(self.line+'\n')
        self.store=CaptureStore(self.root/'store')
        self.archive=self.root/'archive'
        self.ctx=AccessContext('operator')

    def run_import(self):
        return import_jsonl(self.source,self.store,self.archive,self.ctx)

    def test_exact_source_fields_preserved_without_public_or_canon_promotion(self):
        result=self.run_import()
        self.assertEqual(Path(result['original_snapshot']).read_bytes(),self.source.read_bytes())
        row=result['rows'][0]
        snapshot=self.archive/'rows'/(row['row_revision']+'.json')
        self.assertEqual(json.loads(snapshot.read_bytes()),self.original)
        found=self.store.search('cobalt wren',self.ctx)['results']
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['visibility'],'operator')
        self.assertEqual(found[0]['claim_status'],'provisional')
        self.assertFalse(row['receipt']['promoted'])
        with self.assertRaises(AccessDenied):self.store.search('cobalt',AccessContext())
        self.assertEqual(self.store.search('cobalt',AccessContext('gm'))['results'],[])

    def test_replay_append_reorder_and_duplicate_rows_do_not_duplicate_records(self):
        first=self.run_import()
        self.assertEqual(first['new_records'],1)
        self.assertEqual(self.run_import()['new_records'],0)
        second=json.dumps({'fact':'Emerald fox carries a red umbrella.'})
        self.source.write_text(second+'\n'+self.line+'\n'+self.line+'\n')
        appended=self.run_import()
        self.assertEqual(appended['captured_rows'],3)
        self.assertEqual(appended['new_records'],1)
        self.assertEqual(appended['saved_records'],2)
        self.assertEqual(self.run_import()['new_records'],0)
        self.assertEqual(len(list((self.archive/'originals').glob('*.jsonl'))),2)

    def test_malformed_and_missing_text_quarantined_and_accounted_not_dropped(self):
        self.source.write_text(self.line+'\n{bad json\n[]\n'+json.dumps({'fact':42})+'\n'+json.dumps({'fact':'🤠!!!'})+'\n\n')
        result=self.run_import()
        self.assertEqual(result['physical_lines'],6)
        self.assertEqual(result['captured_rows'],1)
        self.assertEqual(result['quarantined_rows'],4)
        self.assertEqual(result['blank_rows'],1)
        self.assertEqual(len(result['rows']),6)

    def test_untrusted_import_has_no_side_effect_and_snapshot_tampering_rejected(self):
        with self.assertRaises(AccessDenied):
            import_jsonl(self.source,self.store,self.archive,AccessContext())
        self.assertFalse(self.archive.exists())
        result=self.run_import()
        Path(result['original_snapshot']).write_text('tampered')
        with self.assertRaises(ValueError):self.run_import()

    def test_interruption_retry_recovers_exactly_once(self):
        real=self.store.capture
        def interrupted(*args,**kwargs):
            real(*args,**kwargs)
            raise RuntimeError('interruption after saved capture')
        self.store.capture=interrupted
        with self.assertRaises(RuntimeError):self.run_import()
        self.store=CaptureStore(self.root/'store')
        retry=self.run_import()
        self.assertEqual(retry['new_records'],0)
        self.assertEqual(retry['saved_records'],1)
        self.assertEqual(retry['searchable_records'],1)

    def test_unrelated_writer_not_counted_as_import_creation(self):
        real=self.store.capture
        injected=False
        def other_writer(*args,**kwargs):
            nonlocal injected
            if not injected:
                injected=True
                real('Unrelated emerald otter.',self.ctx,idempotency_key='other-writer',
                     origin={'doc_id':'other/source','revision':'0'*64})
            return real(*args,**kwargs)
        self.store.capture=other_writer
        result=self.run_import()
        self.assertEqual(result['new_records'],1)
        self.assertEqual(result['observed_store_delta'],2)
