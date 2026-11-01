import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import memory_unification_rules_lineage as lineage


class RulesLineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ocr = self.root / 'ocr'
        self.ocr.mkdir()
        self.target = self.ocr / 'book.md'
        self.target.write_text('===== PAGE 1 =====\nfront matter\n===== PAGE 2 =====\nreal fragment here\nfragment repeated\n')
        self.name = lineage.PREFIX + 'entity.md'
        self.aggregate = self.root / self.name
        self.aggregate.parent.mkdir(parents=True)
        self.queue = self.root / 'queue.json'
        self.save()

    def save(self, excerpt='real fragment', marker=2, reference=None, label='book'):
        ref = reference or str(self.target)
        page = f' p.{marker}' if marker else ''
        self.aggregate.write_text(f'# Entity: Example\n- Reference count: **1**\n'
                                  f'- **{label}**{page} — {excerpt}\n  - Source: `{ref}`\n')
        raw = self.aggregate.read_bytes()
        self.queue.write_text(json.dumps({'version': 1, 'count': 1, 'sources': [
            {'source': self.name, 'revision': lineage.sha(raw), 'bytes': len(raw)}]}))

    def run_trace(self, **kwargs):
        return lineage.trace(self.queue, self.root, self.ocr,
                             kwargs.get('routes', {'book': 'book.md'}),
                             kwargs.get('sources', [self.name]))

    def test_page_bound_match_hashes_not_admission(self):
        report = self.run_trace()
        row = report['rows'][0]
        self.assertEqual(row['status'], 'exact-substring-on-ocr-page')
        self.assertEqual(row['matches'], [{'start_line': 4, 'end_line': 4,
            'passage_sha256': lineage.sha(b'real fragment here')}])
        self.assertEqual(row['original']['revision'], lineage.sha(self.target.read_bytes()))
        self.assertFalse(row['edition_verified'])
        self.assertFalse(row['printed_page_verified'])
        self.assertEqual(report['content_reviews_by_tool'], 0)
        self.assertEqual(report['promoted'], 0)
        self.assertIsNone(report['unique_claims'])

    def test_cross_page_occurrence_cannot_clear_wrong_page(self):
        self.save(marker=1)
        self.assertEqual(self.run_trace()['rows'][0]['status'], 'excerpt-not-found-on-ocr-page')

    def test_short_multiple_fragments_remain_ambiguous(self):
        self.save(excerpt='fragment')
        self.assertEqual(self.run_trace()['rows'][0]['match_count'], 2)

    def test_no_case_whitespace_or_spelling_repair(self):
        for excerpt in ('Real fragment', 'real  fragment', 'real fragments', ''):
            self.save(excerpt=excerpt)
            self.assertEqual(self.run_trace()['rows'][0]['status'], 'excerpt-not-found-on-ocr-page')

    def test_unmapped_secret_reference_never_opened(self):
        self.save(reference='/not-permitted/private', label='unknown')
        row = self.run_trace()['rows'][0]
        self.assertEqual(row['status'], 'unmapped-reference')
        self.assertIsNone(row['original'])

    def test_reference_disagreement_and_unsafe_routes_rejected(self):
        self.save(reference='/not-permitted/private')
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            self.run_trace()
        for route in ('../queue.json', '/absolute/path', '.hidden'):
            with self.assertRaises(ValueError):
                self.run_trace(routes={'book': route})

    def test_missing_and_duplicate_page_markers(self):
        self.save(marker=3)
        self.assertEqual(self.run_trace()['rows'][0]['status'], 'ocr-marker-not-found')
        for text in ('no page markers', '===== PAGE 2 =====\nx\n===== PAGE 2 =====\ny'):
            self.target.write_text(text)
            with self.assertRaisesRegex(ValueError, 'missing or duplicate'):
                self.run_trace()

    def test_unpaginated_does_not_invent_page(self):
        self.save(marker=None)
        row = self.run_trace()['rows'][0]
        self.assertIsNone(row['page_marker'])
        self.assertEqual(row['status'], 'ocr-marker-not-found')

    def test_stale_source_duplicate_selection_and_queue_rejected(self):
        self.aggregate.write_text(self.aggregate.read_text() + 'changed')
        with self.assertRaisesRegex(ValueError, 'revision/size'):
            self.run_trace()
        self.save()
        for names in ([], [self.name, self.name], ['../../secret']):
            with self.assertRaises(ValueError):
                self.run_trace(sources=names)
        q = json.loads(self.queue.read_text())
        q['sources'] *= 2
        q['count'] = 2
        self.queue.write_text(json.dumps(q))
        with self.assertRaisesRegex(ValueError, 'duplicate review queue'):
            self.run_trace()

    def test_symlink_and_overlapping_routes_rejected(self):
        alias = self.ocr / 'alias.md'
        alias.symlink_to(self.target)
        for routes in ({'book': 'alias.md'}, {'book': 'book.md', 'other': 'book.md'}):
            with self.assertRaises(ValueError):
                self.run_trace(routes=routes)

    def test_source_drift_during_trace_rejected(self):
        original = lineage.BoundInputs.verify
        def drift(bound):
            self.target.write_text(self.target.read_text() + 'changed')
            original(bound)
        with patch.object(lineage.BoundInputs, 'verify', drift):
            with self.assertRaisesRegex(ValueError, 'generation changed'):
                self.run_trace()


if __name__ == '__main__':
    unittest.main()
