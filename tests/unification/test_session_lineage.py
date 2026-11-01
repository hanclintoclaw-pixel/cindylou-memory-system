import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import memory_unification_session_lineage as lineage


class SessionLineageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sources, self.originals = self.root/'sources', self.root/'originals'
        self.sources.mkdir(); self.originals.mkdir()
        self.name = 'campaign/sessions/2024-06-06.md'
        self.path = self.sources/self.name
        self.path.parent.mkdir(parents=True)
        self.original = self.originals/'notes_2023-03-23.md'
        self.original.write_text('## 2024-06-06\nPrevious weeks: offered 100.\n')
        self.path.write_text('# Campaign Session: 2024-06-06\n\n- Source chunks: **1**\n'
                             '- Type: session-meta\n\n## Consolidated Notes\n\n'
                             '### Chunk 1 — notes_2023-03-23.md (L2-L2)\n\n'
                             'Previous weeks:  offered 100.\n\nSource: `notes_2023-03-23.md`\n')

    def compare(self, **kwargs):
        return lineage.compare_session(self.name, source_root=self.sources,
            original_roots={'notes': self.originals}, original_prefixes={'notes': 'notes_'},
            bound=lineage.BoundInputs(), **kwargs)

    def test_whitespace_passage_match_is_not_byte_identity(self):
        chunk = self.compare()['chunks'][0]
        self.assertTrue(chunk['whitespace_only_equal'])
        self.assertFalse(chunk['exact_passage_equal'])
        self.assertEqual(chunk['chronology'], 'matching-enclosing-heading')
        self.assertEqual(chunk['enclosing_heading']['start_line'], 1)

    def test_filename_never_overrides_actual_heading(self):
        self.original.write_text('## 2025-07-01\nPrevious weeks: offered 100.\n')
        self.assertEqual(self.compare()['chunks'][0]['chronology'], 'conflicting-enclosing-heading')

    def test_unheaded_original_cannot_get_date_from_filename(self):
        self.original.write_text('\nPrevious weeks: offered 100.\n')
        self.assertEqual(self.compare()['chunks'][0]['chronology'], 'unverified-no-dated-heading')

    def test_generated_ocr_title_is_not_a_human_session_heading(self):
        self.original.write_text('# Imported Scanned Note: 2024-06-06\nPrevious weeks: offered 100.\n')
        self.assertEqual(self.compare()['chunks'][0]['chronology'], 'matching-imported-wrapper-only')

    def test_substantive_change_does_not_normalize_away(self):
        self.original.write_text('## 2024-06-06\nPrevious weeks: paid 100.\n')
        self.assertFalse(self.compare()['chunks'][0]['whitespace_only_equal'])

    def test_cross_section_range_is_flagged(self):
        self.original.write_text('## 2024-06-06\nText\n## 2024-07-11\nMore text\n')
        self.path.write_text(self.path.read_text().replace('(L2-L2)', '(L2-L4)'))
        self.assertEqual(self.compare()['chunks'][0]['chronology'], 'crosses-dated-section')

    def test_multichunk_preserves_two_origins_and_body_boundaries(self):
        other = self.originals/'notes_other.md'
        other.write_text('## 2024-06-06\nSecond source\n')
        self.path.write_text(self.path.read_text().replace('chunks: **1**', 'chunks: **2**')+
            '\n### Chunk 2 — notes_other.md (L2-L2)\n\nSecond source\n\nSource: `notes_other.md`\n')
        result = self.compare()
        self.assertEqual(len(result['chunks']), 2)
        self.assertTrue(all(c['whitespace_only_equal'] for c in result['chunks']))
        self.assertNotEqual(result['chunks'][0]['original']['revision'], result['chunks'][1]['original']['revision'])

    def test_ambiguous_prefix_routes_fail_even_if_only_one_file_exists(self):
        with self.assertRaises(ValueError):
            lineage.compare_session(self.name, source_root=self.sources,
                original_roots={'one': self.originals, 'two': self.sources},
                original_prefixes={'one': 'notes_', 'two': 'notes_'}, bound=lineage.BoundInputs())

    def test_symlink_original_rejected(self):
        self.original.unlink()
        self.original.symlink_to(self.path)
        with self.assertRaises(ValueError): self.compare()

    def test_unbound_trailing_content_rejected(self):
        self.path.write_text(self.path.read_text()+'Unbound claim\n')
        with self.assertRaises(ValueError): self.compare()

    def test_wrong_chunk_count_or_coordinates_rejected(self):
        original = self.path.read_text()
        for changed in [original.replace('chunks: **1**', 'chunks: **2**'),
                        original.replace('(L2-L2)', '(L2-L99)')]:
            self.path.write_text(changed)
            with self.assertRaises(ValueError): self.compare()

    def test_large_passages_are_split_without_lost_lines(self):
        parts = lineage.ranges(('x\n'*401).encode(), 1, 401)
        self.assertEqual([(r['start_line'], r['end_line']) for r in parts], [(1, 200), (201, 400), (401, 401)])
        parts = lineage.ranges(('x'*10000+'\n'+'y'*10000).encode(), 1, 2)
        self.assertEqual(len(parts), 2)

    def test_report_is_mechanical_and_revision_bound(self):
        queue = self.root/'queue.json'
        row = {'source': self.name, 'revision': lineage.sha(self.path.read_bytes())}
        queue.write_text(json.dumps({'version': 1, 'count': 1, 'sources': [row]}))
        result = lineage.run(queue, self.sources, {'notes': self.originals}, {'notes': 'notes_'})
        self.assertEqual(result['content_reviewed_by_this_tool'], 0)
        self.assertEqual(result['promoted'], 0)
        self.assertIsNone(result['unique_claims'])
        self.path.write_text(self.path.read_text().replace('offered 100', 'offered 200'))
        with self.assertRaises(ValueError):
            lineage.run(queue, self.sources, {'notes': self.originals}, {'notes': 'notes_'})

    def test_original_drift_during_measurement_rejected(self):
        original_compare = lineage.compare_session
        def drift(*args, **kwargs):
            result = original_compare(*args, **kwargs)
            self.original.write_text('Changed during comparison\n')
            return result
        queue = self.root/'queue.json'
        queue.write_text(json.dumps({'version': 1, 'count': 1, 'sources': [
            {'source': self.name, 'revision': lineage.sha(self.path.read_bytes())}]}))
        with patch.object(lineage, 'compare_session', side_effect=drift):
            with self.assertRaisesRegex(ValueError, 'changed during review'):
                lineage.run(queue, self.sources, {'notes': self.originals}, {'notes': 'notes_'})


if __name__ == '__main__':
    unittest.main()
