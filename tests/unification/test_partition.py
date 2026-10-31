import hashlib
from pathlib import Path
import tempfile
import unittest

from unification.partition import materialize_public, validate_public
from unification.policy import Approval, Registry, Section, Source, StaleReference


class PartitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/'mixed.md'
        self.path.write_text('Public emerald hamster.\nGM secret violet otter.\n')
        self.approval=Approval('mixed.md',hashlib.sha256(self.path.read_bytes()).hexdigest(),(
            Section('public',1,1,'public','provisional'),Section('gm',2,2,'gm','provisional')))
        self.registry=Registry([Source('wiki',self.root,approvals=(self.approval,))])
        self.target=self.root/'view'
        self.manifest=materialize_public(self.registry,self.target)

    def test_export_contains_public_passage_only_and_exact_mapping(self):
        self.assertEqual(len(self.manifest['records']),1)
        record=self.manifest['records'][0]
        raw=(self.target/'workspace'/record['path']).read_text()
        self.assertIn('emerald',raw)
        self.assertNotIn('violet',raw)
        self.assertEqual(record['evidence']['claim_status'],'provisional')
        self.assertEqual(record['evidence']['doc_id'],'wiki/mixed.md#public')
        validate_public(self.registry,self.target,self.manifest)

    def test_generation_cannot_reuse_old_directory(self):
        with self.assertRaises(FileExistsError):
            materialize_public(self.registry,self.target)

    def test_changed_source_cannot_use_old_view(self):
        self.path.write_text('Revised public and private text.')
        with self.assertRaises(StaleReference):
            validate_public(self.registry,self.target,self.manifest)

    def test_revoked_or_reclassified_source_invalidates_whole_view(self):
        for registry in [Registry([]),Registry([Source('wiki',self.root,approvals=(Approval('mixed.md',self.approval.revision,(
                        Section('public',1,1,'gm'),Section('gm',2,2,'gm'))),))])]:
            with self.assertRaises(StaleReference):
                validate_public(registry,self.target,self.manifest)

    def test_added_native_root_memory_file_is_rejected(self):
        (self.target/'workspace/MEMORY.md').write_text('Private surprise.')
        with self.assertRaises(StaleReference):
            validate_public(self.registry,self.target,self.manifest)

    def test_tampered_view_or_mapped_path_is_rejected(self):
        path=self.target/'workspace'/self.manifest['records'][0]['path']
        path.write_text('Tampered private content.')
        with self.assertRaises(StaleReference):
            validate_public(self.registry,self.target,self.manifest)
        self.manifest['records'][0]['path']='../mixed.md'
        with self.assertRaises(StaleReference):
            validate_public(self.registry,self.target,self.manifest)

    def test_symlink_view_is_rejected(self):
        path=self.target/'workspace'/self.manifest['records'][0]['path']
        path.unlink();path.symlink_to(self.path)
        with self.assertRaises(StaleReference):
            validate_public(self.registry,self.target,self.manifest)


if __name__=='__main__':
    unittest.main()
