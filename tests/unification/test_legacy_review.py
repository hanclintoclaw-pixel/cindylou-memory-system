import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('legacy_review', Path(__file__).resolve().parents[2]/'scripts/memory_unification_legacy_review.py')
reviewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer)


class LegacyReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.sources = self.root/'sources'
        self.originals = self.root/'originals'
        self.sources.mkdir(); self.originals.mkdir()
        (self.sources/'entity.md').write_text('# Entity\nHistorical claim\n')
        (self.originals/'original.md').write_text('# Entity\nHistorical claim\n')
        raw = (self.sources/'entity.md').read_bytes()
        self.revision = reviewer.sha(raw)
        self.queue = self.root/'queue.json'
        self.queue.write_text(json.dumps({'version': 1, 'count': 1, 'sources': [
            {'review_id': 'review-1', 'source': 'entity.md', 'revision': self.revision, 'bytes': len(raw)}]}))
        self.payload = {'version': 1, 'kind': 'private-legacy-semantic-review',
                        'reviewer': 'test-reviewer', 'review_scope': 'entire-listed-files',
                        'queue_sha256': reviewer.sha(self.queue.read_bytes()),
                        'visibility': 'operator', 'promoted': 0, 'unique_claims': None,
                        'reviews': [{'source': 'entity.md', 'revision': self.revision,
                            'review_status': 'reviewed-not-promoted', 'lineage_status': 'historical-passage-verified', 'findings': [{
                                'classification': 'historical-source-supported', 'rationale': 'Reviewed source supports this dated passage, not current status.',
                                'start_line': 2, 'end_line': 2,
                                'passage_sha256': reviewer.sha(b'Historical claim'),
                                'evidence': [{'root': 'originals', 'path': 'original.md',
                                    'revision': self.revision, 'start_line': 2, 'end_line': 2,
                                    'passage_sha256': reviewer.sha(b'Historical claim'),
                                    'relation': 'same-byte-copy'}]}]}]}

    def validate(self, payload=None):
        return reviewer.validate_review(payload or self.payload, queue_path=self.queue,
            source_root=self.sources, evidence_roots={'originals': self.originals})

    def test_real_sources_duplicate_triage_is_not_semantic_review(self):
        result = reviewer.inventory(self.queue, self.sources, [self.originals])
        self.assertEqual(result['exact_comparison_copy_count'], 1)
        self.assertEqual(result['semantic_reviewed'], 0)
        self.assertIsNone(result['unique_claims'])
        self.assertEqual(result['promoted'], 0)

    def test_review_binds_findings_and_lineage(self):
        result = self.validate()
        self.assertEqual(result['reviewed_files'], 1)
        self.assertEqual(result['remaining_files'], 0)
        self.assertIsNone(result['unique_claims'])

    def test_queue_drift_blocks_review_and_inventory(self):
        (self.sources/'entity.md').write_text('Changed canonical source\n')
        with self.assertRaises(ValueError): self.validate()
        with self.assertRaises(ValueError): reviewer.inventory(self.queue, self.sources)

    def test_lineage_drift_blocks_attestation(self):
        (self.originals/'original.md').write_text('Changed original\n')
        with self.assertRaises(ValueError): self.validate()

    def test_wrong_bounded_passage_rejected(self):
        self.payload['reviews'][0]['findings'][0]['evidence'][0]['passage_sha256'] = '0'*64
        with self.assertRaises(ValueError): self.validate()

    def test_false_copy_claim_rejected_even_with_current_hashes(self):
        (self.originals/'original.md').write_text('Different heading\nHistorical claim\n')
        self.payload['reviews'][0]['findings'][0]['evidence'][0]['revision'] = reviewer.sha((self.originals/'original.md').read_bytes())
        with self.assertRaises(ValueError): self.validate()

    def test_no_promoted_or_public_annotations(self):
        for key, value in [('promoted', 1), ('visibility', 'public'), ('unique_claims', 2)]:
            payload = copy.deepcopy(self.payload)
            payload[key] = value
            with self.assertRaises(ValueError): self.validate(payload)

    def test_duplicate_review_cannot_inflate_count(self):
        self.payload['reviews'].append(copy.deepcopy(self.payload['reviews'][0]))
        with self.assertRaises(ValueError): self.validate()

    def test_missing_lineage_completeness_rejected(self):
        del self.payload['reviews'][0]['lineage_status']
        with self.assertRaises(ValueError): self.validate()

    def test_traversal_symlink_and_hidden_sources_rejected(self):
        (self.sources/'link.md').symlink_to(self.originals/'original.md')
        for relative in ('../originals/original.md', 'link.md', '/etc/passwd', '.hidden.md'):
            with self.assertRaises(ValueError): reviewer.safe_file(self.sources, relative)

    def test_new_receipts_never_overwrite(self):
        target = self.root/'receipt.json'
        reviewer.write_new(target, {'retained': True})
        with self.assertRaises(FileExistsError): reviewer.write_new(target, {'retained': False})
        self.assertEqual(json.loads(target.read_text()), {'retained': True})


if __name__ == '__main__':
    unittest.main()
