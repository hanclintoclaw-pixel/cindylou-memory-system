import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import memory_unification_rules_derivatives as triage


class RulesDerivativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.name = triage.PREFIX + 'browse.md'
        self.file = self.root / self.name
        self.file.parent.mkdir(parents=True)
        # A dangerous reference must remain inert, even though it looks like a path.
        self.raw = ('# Entity: Browse\n\n- Reference count: **1**\n\n## Cited Mentions\n\n'
                    '- **sourcebooks__SR3_example** p.12 — shoppers browse\n'
                    '  - Source: `/never-open-this/private-secret`\n').encode()
        self.file.write_bytes(self.raw)
        self.queue = self.root / 'queue.json'
        self.save_queue()

    def save_queue(self, duplicate=False):
        item = {'source': self.name, 'revision': hashlib.sha256(self.raw).hexdigest(),
                'bytes': len(self.raw)}
        rows = [item, item] if duplicate else [item]
        self.queue.write_text(json.dumps({'version': 1, 'count': len(rows), 'sources': rows}))

    def test_reference_is_not_opened_or_edition_admitted(self):
        report = triage.inventory(self.queue, self.root)
        self.assertEqual(report['content_reviewed_by_this_tool'], 0)
        self.assertEqual(report['sources'][0]['citations'][0]['reference_status'], 'not-opened')
        self.assertEqual(report['sources'][0]['admission'], 'quarantined-unverified')
        self.assertIsNone(report['unique_claims'])
        self.assertEqual(report['promoted'], 0)

    def test_windows_cover_every_line_and_respect_both_budgets(self):
        raw = ('alpha\n\nbeta\ngamma\ndelta\n').encode()
        spans = triage.windows(raw, max_chars=10, max_lines=2)
        lines = raw.decode().splitlines()
        restored = []
        for p in spans:
            section = lines[p['start_line']-1:p['end_line']]
            restored.extend(section)
            text = '\n'.join(section)
            self.assertLessEqual(len(text), 10)
            self.assertLessEqual(len(section), 2)
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), p['passage_sha256'])
        self.assertEqual(restored, lines)

    def test_oversized_line_and_invalid_budgets_refused(self):
        for kwargs in ({'max_chars': True}, {'max_lines': 201}, {'max_chars': 0}):
            with self.assertRaises(ValueError):
                triage.windows(b'x', **kwargs)
        with self.assertRaisesRegex(ValueError, 'single line'):
            triage.windows(b'longline', max_chars=3)

    def test_broken_pair_and_declared_count_refused(self):
        with self.assertRaisesRegex(ValueError, 'adjacent'):
            triage.parse_aggregate(self.raw.replace(b'  - Source:', b'bad Source:'))
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            triage.parse_aggregate(self.raw.replace(b'count: **1**', b'count: **2**'))

    def test_unrecognized_prose_remains_visible_not_silently_discarded(self):
        parsed = triage.parse_aggregate(self.raw + b'Unknown new claim here.\n')
        self.assertEqual(len(parsed['unparsed_lines']), 1)
        self.assertEqual(parsed['unparsed_lines'][0]['line'], 9)

    def test_changed_source_and_duplicate_queue_refused(self):
        self.file.write_bytes(self.raw + b'changed\n')
        with self.assertRaisesRegex(ValueError, 'revision/size'):
            triage.inventory(self.queue, self.root)
        self.file.write_bytes(self.raw)
        self.save_queue(duplicate=True)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            triage.inventory(self.queue, self.root)

    def test_symlink_source_refused(self):
        target = self.root / 'other'
        self.file.rename(target)
        self.file.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            triage.inventory(self.queue, self.root)

    def test_bounded_read_and_invalid_source_window(self):
        result = triage.read_window(self.queue, self.root, self.name, 1)
        self.assertEqual(result['text'], '\n'.join(self.raw.decode().splitlines()))
        for name, window in ((self.name, 2), (self.name, 0), ('../../secret', 1)):
            with self.assertRaises(ValueError):
                triage.read_window(self.queue, self.root, name, window)

    def test_drift_during_inventory_rejected(self):
        original = triage.BoundInputs.verify
        def drift(bound):
            self.file.write_bytes(self.raw + b'drift\n')
            original(bound)
        with patch.object(triage.BoundInputs, 'verify', drift):
            with self.assertRaisesRegex(ValueError, 'generation changed'):
                triage.inventory(self.queue, self.root)

    def test_repeated_row_count_is_not_a_claim_count(self):
        other = self.file.with_name('browse.description.md')
        other.write_bytes(self.raw)
        queue = json.loads(self.queue.read_text())
        queue['sources'].append({**queue['sources'][0], 'source': str(other.relative_to(self.root))})
        queue['count'] = 2
        self.queue.write_text(json.dumps(queue))
        report = triage.inventory(self.queue, self.root)
        self.assertEqual(report['citation_rows'], 2)
        self.assertEqual(report['repeated_identical_label_marker_excerpt_rows'], 1)
        self.assertIsNone(report['unique_claims'])

    def test_unpaginated_campaign_or_homebrew_row_not_lost(self):
        raw = self.raw.replace(b'**sourcebooks__SR3_example** p.12', b'**Wordpress/Homebrew**')
        parsed = triage.parse_aggregate(raw)
        self.assertEqual(parsed['citation_count'], 1)
        self.assertIsNone(parsed['citations'][0]['page_marker'])
        self.assertEqual(parsed['citations'][0]['page_kind'], 'unpaginated-source-not-a-book-citation')
        self.assertEqual(parsed['unparsed_lines'], [])


if __name__ == '__main__':
    unittest.main()
