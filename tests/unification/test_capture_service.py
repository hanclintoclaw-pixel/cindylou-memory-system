import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from unification.capture import CaptureStore
from unification.policy import AccessContext, AccessDenied, Registry, StaleReference
from unification.service import MemoryService


class CaptureServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=CaptureStore(self.root/'store')
        self.service=MemoryService(Registry([]),captures=self.store)
        self.ctx=AccessContext('operator')
        self.origin={'doc_id':'private/test','revision':'0'*64}

    def test_shared_save_search_bounded_get_revision_and_public_denial(self):
        receipt=self.service.capture('Cobalt wren.\nBlue hat.',self.ctx,idempotency_key='key',origin=self.origin)
        self.assertTrue(receipt['saved'] and receipt['searchable'])
        self.assertFalse(receipt['promoted'])
        found=self.service.search('cobalt wren',self.ctx,domain='captured')
        evidence=found['results'][0]
        self.assertEqual(evidence['claim_status'],'provisional')
        got=self.service.get(evidence['doc_id'],self.ctx,revision=evidence['revision'],start_line=2,lines=1)
        self.assertEqual(got['text'],'Blue hat.')
        self.assertEqual(got['source_line'],2)
        self.assertNotIn('excerpt',got)
        self.assertNotIn('Cobalt wren.',json.dumps(got))
        with self.assertRaises(StaleReference):self.service.get(evidence['doc_id'],self.ctx,revision='1'*64)
        with self.assertRaises(AccessDenied):self.service.search('cobalt',AccessContext(),domain='captured')
        with self.assertRaises(AccessDenied):self.service.get(evidence['doc_id'],AccessContext())
        with self.assertRaises(ValueError):self.service.get(evidence['doc_id'],self.ctx,lines=201)

    def test_missing_store_explicit_unavailable_not_fallback(self):
        service=MemoryService(Registry([]))
        self.assertEqual(service.search('x',self.ctx,domain='captured')['status'],'unavailable')
        self.assertFalse(service.capture('x',self.ctx,idempotency_key='k',origin=self.origin)['saved'])
        with self.assertRaises(ValueError):self.service.search('x',self.ctx,domain='captured',mode='hybrid')

    def test_stale_derivative_get_never_labels_old_claim_current(self):
        first=self.service.capture('Cobalt wren old balance.',self.ctx,idempotency_key='first',origin=self.origin)
        copy=self.service.capture('Cobalt wren derivative.',self.ctx,idempotency_key='copy',origin=self.origin,
            derivative_of=first['record_id'])
        self.service.capture('Cobalt wren corrected balance.',self.ctx,idempotency_key='fix',origin=self.origin,
            supersedes=first['record_id'])
        old=self.service.get('capture/'+copy['record_id'],self.ctx)
        self.assertEqual(old['record_status'],'stale-derivative')
        self.assertEqual(old['claim_status'],'superseded')
        self.assertEqual(self.service.search('derivative',self.ctx,domain='captured')['results'],[])

    def test_actual_opt_in_local_cli_uses_same_contract(self):
        origin=self.root/'origin.json'
        origin.write_text(json.dumps(self.origin))
        cmd=[sys.executable,'-m','unification.capture_cli','--store',str(self.root/'cli-store')]
        saved=subprocess.run(cmd+['save','--origin-file',str(origin),'--idempotency-key','one'],
            input='Emerald fox under an umbrella.',text=True,capture_output=True,check=True)
        receipt=json.loads(saved.stdout)
        self.assertTrue(receipt['saved'] and receipt['searchable'])
        result=subprocess.run(cmd+['search','--q','emerald fox'],text=True,capture_output=True,check=True)
        evidence=json.loads(result.stdout)['results'][0]
        self.assertEqual(evidence['revision'],receipt['revision'])
        self.assertEqual(evidence['visibility'],'operator')
        self.assertFalse(evidence['promoted'])
