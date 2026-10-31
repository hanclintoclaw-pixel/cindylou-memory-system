import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unification.policy import AccessContext, AccessDenied, Approval, Registry, Section, Source, StaleReference
from unification.registry import load_registry
from unification.service import MemoryService


class SectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'mixed.md'
        self.path.write_text('# Known\nEmerald lives in Nashville.\n# Draft\nSecret violet-otter ambush.\n# Disputed\nEmerald owes ten credits.\nUnreviewed trailing secret.\n')
        self.sections = (Section('known',1,2,'public','confirmed','campaign-canon'),
                         Section('draft',3,4,'gm','provisional','generated-draft'),
                         Section('disputed',5,6,'public','disputed','table-evidence'))
        self.approval = Approval('mixed.md',hashlib.sha256(self.path.read_bytes()).hexdigest(), self.sections)
        self.registry = Registry([Source('wiki',self.root,domain='campaign',approvals=(self.approval,))])
        self.service = MemoryService(self.registry)
        self.public = AccessContext()

    def test_mixed_page_search_does_not_score_private_or_unreviewed_text(self):
        self.assertEqual(self.service.search('violet otter ambush secret',self.public)['results'],[])
        hits = self.service.search('Emerald',self.public)['results']
        self.assertEqual({h['doc_id'] for h in hits}, {'wiki/mixed.md#known','wiki/mixed.md#disputed'})
        self.assertNotIn('Secret',json.dumps(hits))
        self.assertNotIn('Unreviewed',json.dumps(hits))
        self.assertEqual({h['claim_status'] for h in hits},{'confirmed','disputed'})
        self.assertEqual({h['evidence_group'] for h in hits},{'wiki/mixed.md'})

    def test_public_direct_get_and_guessing_draft_denied(self):
        for ref in ['wiki/mixed.md','wiki/mixed.md#draft','wiki/mixed.md#unknown','wiki/mixed.md#known#draft']:
            with self.subTest(ref=ref), self.assertRaises(AccessDenied):
                self.service.get(ref,self.public)
        got = self.service.get('wiki/mixed.md#known',self.public)
        self.assertEqual(got['text'],'# Known\nEmerald lives in Nashville.')
        self.assertEqual(got['status'],'ok')
        self.assertEqual(got['claim_status'],'confirmed')
        self.assertEqual(got['citation']['end_line'],2)

    def test_gm_read_preserves_draft_status(self):
        got = self.service.get('wiki/mixed.md#draft',AccessContext('gm'))
        self.assertIn('violet-otter',got['text'])
        self.assertEqual(got['claim_status'],'provisional')
        self.assertEqual(got['authority'],'generated-draft')
        self.assertEqual(got['source_line'],3)

    def test_edited_approval_fails_even_without_old_search_reference(self):
        # Adding a private line inside a previously approved section must not leak
        # through a fresh query or a direct get that omitted the old revision.
        self.path.write_text(self.path.read_text().replace('Emerald lives','Secret new-lynx. Emerald lives'))
        for call in [lambda:self.service.search('new lynx',self.public),
                     lambda:self.service.get('wiki/mixed.md#known',self.public)]:
            with self.assertRaises(StaleReference):
                call()

    def test_read_bounds_are_section_relative_but_citation_is_source_relative(self):
        got = self.service.get('wiki/mixed.md#disputed',self.public,start_line=2,lines=1)
        self.assertEqual(got['source_line'],6)
        self.assertEqual(got['text'],'Emerald owes ten credits.')
        self.assertEqual(got['citation']['start_line'],5)
        hit = self.service.search('credits',self.public)['results'][0]
        self.assertGreaterEqual(hit['start_line'],5)
        self.assertLessEqual(hit['end_line'],6)

    def test_single_partial_section_has_no_whole_page_alias(self):
        registry = Registry([Source('wiki',self.root,approvals=(Approval('mixed.md',self.approval.revision,(self.sections[0],)),))])
        with self.assertRaises(AccessDenied):
            registry.read('wiki/mixed.md',self.public)
        self.assertNotIn('Secret',registry.read('wiki/mixed.md#known',self.public).content)

    def test_fifo_replacement_is_rejected_without_blocking(self):
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaises(AccessDenied):
            self.registry.read('wiki/mixed.md#known',self.public)

    def test_approval_revocation_during_io(self):
        original = self.registry._resolve
        calls=[]
        def resolving(*args):
            calls.append(1)
            if len(calls) == 2:
                self.registry.sources.clear()
            return original(*args)
        with patch.object(self.registry,'_resolve',side_effect=resolving), self.assertRaises(AccessDenied):
            self.registry.read('wiki/mixed.md#known',self.public)

    def test_approval_revocation_during_ranking(self):
        original = self.registry.documents
        def documents(*args):
            yield from original(*args)
            self.registry.sources.clear()
        with patch.object(self.registry,'documents',side_effect=documents), self.assertRaises(AccessDenied):
            self.service.search('Emerald',self.public)

    def test_bad_hash_ranges_duplicates_and_mutable_approvals_rejected(self):
        for build in [lambda:Approval('mixed.md','not-a-hash',self.sections),
                      lambda:Approval('../mixed.md','0'*64,self.sections),
                      lambda:Approval('mixed.md','0'*64,(self.sections[0],self.sections[0])),
                      lambda:Approval('mixed.md','0'*64,(Section('a',1,3),Section('b',3,4))),
                      lambda:Section('a',True,4),
                      lambda:Source('wiki',self.root,approvals=[self.approval])]:
            with self.subTest(build=build), self.assertRaises(ValueError):
                build()

    def test_out_of_bounds_approved_section_is_not_silently_clipped(self):
        source=Source('wiki',self.root,approvals=(Approval('mixed.md',self.approval.revision,(Section('bad',1,100,'public'),)),))
        with self.assertRaises(ValueError):
            Registry([source]).read('wiki/mixed.md#bad',self.public)

    def test_v2_manifest_loads_sections_and_old_blanket_schema_is_rejected(self):
        from dataclasses import asdict
        manifest=self.root/'registry.json'
        payload={'version':2,'sources':[{'namespace':'wiki','root':str(self.root),'approvals':[asdict(self.approval)]}]}
        manifest.write_text(json.dumps(payload))
        self.assertEqual(load_registry(manifest).read('wiki/mixed.md#known',self.public).section.status,'confirmed')
        payload['sources'][0]['approvals'][0]['sections'][0]['audience']='operator'
        manifest.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            load_registry(manifest)


if __name__ == '__main__':
    unittest.main()
