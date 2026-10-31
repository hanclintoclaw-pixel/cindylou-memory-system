import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from unification.registry import load_registry
from unification.service import MemoryService
from unification.policy import AccessContext


class RegistryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'public.md').write_text('Public emerald hamster.')
        (self.root/'private.md').write_text('Private sapphire ferret.')
        self.manifest=self.root/'registry.json'
        self.payload={'version':2,'sources':[
            {'namespace':'shared','root':str(self.root),'approvals':[self.approval('public.md','public')]},
            {'namespace':'ops','root':str(self.root),'approvals':[self.approval('private.md','operator')]}]}
        self.save()

    def approval(self, filename, visibility):
        return {'path':filename,'revision':hashlib.sha256((self.root/filename).read_bytes()).hexdigest(),
                'sections':[{'section_id':'whole','start_line':1,'end_line':1,'visibility':visibility}]}

    def save(self):
        self.manifest.write_text(json.dumps(self.payload))

    def invoke(self,*args):
        run=subprocess.run([sys.executable,'-m','unification.cli','--registry',str(self.manifest),*args],
                           capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,0,run.stderr)
        return json.loads(run.stdout)

    def test_public_cli_search_then_bounded_read(self):
        search=self.invoke('search','--q','hamster')
        self.assertEqual(search['coverage'],'partial')
        hit=search['results'][0]
        got=self.invoke('get',hit['doc_id'],'--revision',hit['revision'])
        self.assertIn('emerald hamster',got['text'])
        self.assertEqual(got['citation'],hit['citation'])

    def test_public_cli_cannot_gain_operator_rights(self):
        self.assertEqual(self.invoke('search','--q','sapphire ferret')['results'],[])
        self.assertEqual(self.invoke('get','ops/private.md')['status'],'denied')
        run=subprocess.run([sys.executable,'-m','unification.cli','--registry',str(self.manifest),
                            '--audience','operator','get','ops/private.md'],capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0)

    def test_manifest_schema_and_explicit_approval_required(self):
        for broken in [{'version':1,'sources':[]},
                       {'version':1,'sources':[{'namespace':'x','root':str(self.root)}]},
                       {'version':1,'sources':[{'namespace':'x','root':'.','approved':[]}]}]:
            self.manifest.write_text(json.dumps(broken))
            with self.assertRaises(ValueError):
                load_registry(self.manifest)

    def test_unavailable_native_reported_in_real_cli(self):
        result=self.invoke('search','--q','hamster','--mode','hybrid')
        self.assertEqual(result['results'],[])
        self.assertEqual(result['backends'][0]['status'],'unavailable')

    def test_synthetic_duplicate_views_share_evidence_group(self):
        self.payload['sources'][0]['evidence_group']='underlying-source-A'
        self.save()
        service=MemoryService(load_registry(self.manifest))
        hit=service.search('hamster',AccessContext())['results'][0]
        self.assertEqual(hit['evidence_group'],'underlying-source-A')


if __name__ == '__main__':
    unittest.main()
