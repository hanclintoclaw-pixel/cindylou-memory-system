"""Scratch-only counterexamples. No reader, model, service or native imports."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.memory_unification_isolation import main
from unification.isolation import (Rejected, ScratchWorkspace, SyntheticAuthority,
    SyntheticSupervisor, execution_gate, load_prepared_cases, scratch_generation,
    synthetic_grade)


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()
        self.parent.chmod(0o700)
        self.workspace = ScratchWorkspace(self.parent)
        self.addCleanup(self.workspace.close)
        self.workspace.write_json('source.json', {'text': 'cobalt wren'})
        self.source = self.workspace.path / 'source.json'
        self.generation = scratch_generation(self.workspace, [self.source])
        self.authority = SyntheticAuthority()
        self.context = self.authority.mint()
        self.supervisor = SyntheticSupervisor(self.workspace, self.authority, self.generation, enabled=True)
        self.expected = {'doc_id': 'synthetic/page', 'revision': self.generation[str(self.source)]['sha256'], 'required_terms': ['cobalt wren']}
        self.response = {'status': 'ok', 'results': [{'doc_id': 'synthetic/page'}],
                         'passage': {'doc_id': 'synthetic/page', 'revision': self.expected['revision'],
                                     'eligible': True, 'start_line': 1, 'end_line': 1, 'text': 'cobalt wren'}}

    def finish(self, attempt, **kwargs):
        return self.supervisor.finish(attempt, kwargs.get('query', 'q'), kwargs.get('context', self.context),
            self.expected, {'legacy': self.response, 'unified': self.response})

    def test_default_off_and_all_real_lanes_unavailable(self):
        self.assertEqual(execution_gate()['reason'], 'default-off')
        for lane in ['private-native', 'native', 'legacy', 'model', 'http', 'tool', 'operator', 'session']:
            self.assertEqual(execution_gate(enabled=True, lane=lane)['status'], 'unavailable')
        with self.assertRaises(Rejected):
            SyntheticSupervisor(self.workspace, self.authority, self.generation)

    def test_cli_gates_before_input_output_import_or_process(self):
        original_import = __import__
        def guarded_import(name, *args, **kwargs):
            if name.startswith(('unification', 'memory_bridge')):
                raise AssertionError('reader/scaffolding import attempted')
            return original_import(name, *args, **kwargs)
        with patch('pathlib.Path.read_bytes', side_effect=AssertionError('input touched')), patch('builtins.__import__', side_effect=guarded_import), patch('subprocess.run', side_effect=AssertionError('process attempted')):
            for args in [[], ['--enable-synthetic', '--lane', 'private-native'], ['--enable-synthetic', '--lane', 'native']]:
                with patch('sys.stdout', new=io.StringIO()) as stdout:
                    self.assertEqual(main(args), 0)
                    self.assertEqual(json.loads(stdout.getvalue())['status'], 'unavailable')

    def test_positive_is_only_synthetic_passage_not_final_correctness(self):
        result = self.finish(self.supervisor.begin('q', self.context))
        self.assertTrue(all(g['eligible_bounded_passage'] for g in result['grades'].values()))
        self.assertEqual(result['grades']['legacy']['final_answer_correctness'], 'not-assessed')
        self.assertFalse(result['production_write_denial_proven'])
        self.assertFalse(result['host_authority_proven'])
        self.assertEqual(result['descendants_started'], 0)

    def test_document_id_without_fact_fails(self):
        for passage in [{}, {**self.response['passage'], 'text': 'Nothing relevant'}]:
            result = synthetic_grade(self.expected, {'status': 'ok', 'results': self.response['results'], 'passage': passage})
            self.assertTrue(result['candidate_retrieval'])
            self.assertFalse(result['eligible_bounded_passage'])

    def test_stale_ineligible_unbounded_or_wrong_doc_passages_fail(self):
        for changes in [{'revision': '0'*64}, {'eligible': False}, {'start_line': 0}, {'end_line': 100},
                        {'text': 'cobalt wren' + 'x'*6000}, {'doc_id': 'other'}, {'start_line': True}]:
            response = copy.deepcopy(self.response)
            response['passage'].update(changes)
            self.assertFalse(synthetic_grade(self.expected, response)['eligible_bounded_passage'])

    def test_policy_ranking_ingestion_unknown_unavailable_distinct(self):
        for status in ['policy-excluded', 'ranking-miss', 'ingestion-gap', 'unknown', 'unavailable']:
            response = {**self.response, 'status': status}
            grade = synthetic_grade(self.expected, response)
            self.assertEqual(grade['backend_state'], status)
            self.assertFalse(grade['eligible_bounded_passage'])
            self.assertEqual(grade['loss'], 'unknown')

    def test_missing_forged_unknown_and_other_issuer_context_rejected(self):
        other = SyntheticAuthority()
        for token in [None, object(), {'audience': 'operator', 'session': 'guessed'}, other.mint()]:
            with self.assertRaises(Rejected):
                self.supervisor.begin('q', token)

    def test_revocation_before_and_after_begin_rejected(self):
        attempt = self.supervisor.begin('q', self.context)
        self.authority.revoke(self.context)
        with self.assertRaises(Rejected):
            self.finish(attempt)
        with self.assertRaises(Rejected):
            self.supervisor.begin('q', self.context)

    def test_expired_context_rejected(self):
        with patch('unification.isolation.time.monotonic', return_value=10**30):
            with self.assertRaises(Rejected):
                self.supervisor.begin('q', self.context)

    def test_same_query_context_required_and_attempt_not_replayable(self):
        for kwargs in [{'query': 'changed'}, {'context': self.authority.mint()}]:
            attempt = self.supervisor.begin('q', self.context)
            with self.assertRaises(Rejected):
                self.finish(attempt, **kwargs)
        attempt = self.supervisor.begin('q', self.context)
        self.finish(attempt)
        with self.assertRaises(Rejected):
            self.finish(attempt)

    def test_content_drift_under_same_path_and_restored_mtime_rejected(self):
        attempt = self.supervisor.begin('q', self.context)
        before = self.source.stat()
        self.source.write_bytes(self.source.read_bytes().replace(b'cobalt', b'silver'))
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(Rejected):
            self.finish(attempt)

    def test_every_enumerated_code_registry_partition_member_is_bound(self):
        for name in ['code', 'registry', 'partition']:
            self.workspace.write_json(name + '.json', {'identity': name})
        paths = [self.source, *[self.workspace.path / (n + '.json') for n in ['code', 'registry', 'partition']]]
        generation = scratch_generation(self.workspace, paths)
        supervisor = SyntheticSupervisor(self.workspace, self.authority, generation, enabled=True)
        generation[str(self.source)]['sha256'] = 'caller mutation must not alter stored pin'
        attempt = supervisor.begin('q', self.context)
        (self.workspace.path / 'registry.json').write_text('{"changed":true}')
        with self.assertRaises(Rejected):
            supervisor.finish(attempt, 'q', self.context, self.expected, {'legacy': self.response, 'unified': self.response})

    def test_missing_generation_member_and_forged_hash_rejected(self):
        for generation in [{str(self.source): {**self.generation[str(self.source)], 'sha256': '0'*64}}, {}]:
            supervisor = SyntheticSupervisor(self.workspace, self.authority, generation, enabled=True)
            with self.assertRaises(Rejected):
                supervisor.begin('q', self.context)
        self.source.rename(self.workspace.path / 'moved.json')
        with self.assertRaises(FileNotFoundError):
            self.supervisor.begin('q', self.context)

    def test_generation_outside_scratch_rejected(self):
        outside = self.parent / 'outside.json'
        outside.write_text('{}')
        with self.assertRaises(Rejected):
            scratch_generation(self.workspace, [outside])

    def test_output_traversal_absolute_symlink_and_replace_rejected(self):
        for name in ['../escape.json', '/tmp/escape.json', 'sub/out.json', '.', 'x\\out.json']:
            with self.assertRaises(Rejected):
                self.workspace.write_json(name, {})
        self.workspace.write_json('exists.json', {})
        with self.assertRaises(FileExistsError):
            self.workspace.write_json('exists.json', {'replace': True})
        target = self.parent / 'target'
        target.write_text('unchanged')
        (self.workspace.path / 'link.json').symlink_to(target)
        with self.assertRaises(FileExistsError):
            self.workspace.write_json('link.json', {})
        self.assertEqual(target.read_text(), 'unchanged')

    def test_unsafe_parent_permissions_protected_roots_and_symlink_rejected(self):
        with self.assertRaises(Rejected):
            ScratchWorkspace(self.parent, forbidden_roots=[self.parent])
        self.parent.chmod(0o755)
        with self.assertRaises(Rejected):
            ScratchWorkspace(self.parent)
        self.parent.chmod(0o700)
        link = self.parent / 'alias'
        link.symlink_to(self.workspace.path)
        with self.assertRaises(Rejected):
            ScratchWorkspace(link)

    def test_closed_or_renamed_workspace_cannot_publish(self):
        self.workspace.close()
        with self.assertRaises(Rejected):
            self.workspace.write_json('closed.json', {})
        workspace = ScratchWorkspace(self.parent)
        self.addCleanup(workspace.close)
        moved = self.parent / 'moved'
        workspace.path.rename(moved)
        workspace.path.mkdir()
        with self.assertRaises(Rejected):
            workspace.write_json('changed.json', {})


class PreparedCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root / 'source'
        source.write_text('Synthetic source only')
        revision = hashlib.sha256(source.read_bytes()).hexdigest()
        self.source = source
        case = {'query': 'synthetic?', 'query_sha256': hashlib.sha256(b'synthetic?').hexdigest(),
                'expected_answer_rubric': 'unresolved', 'rubric_limits': 'not factual clearance',
                'retained_status': 'private-provisional-unresolved-not-promoted',
                'summary_binding': {'path': str(source), 'revision': revision}, 'supporting_passages': []}
        self.design = {'packets': {str(source): revision}, 'unique_claims': None, 'promoted': 0,
            'cases': [{**case, 'case_id': f'CP{pilot}-{n:02}', 'originating_evidence_group': str(n % 2)}
                      for pilot, count in [(18, 10), (19, 9)] for n in range(1, count+1)]}
        self.path = self.root / 'design.json'

    def save(self):
        self.path.write_text(json.dumps(self.design))
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_consumption_keeps_all_cases_private_unavailable_and_original_bytes(self):
        revision = self.save()
        before = self.path.read_bytes()
        inventory = load_prepared_cases(self.path, revision)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(inventory['case_count'], 19)
        self.assertEqual(inventory['origin_groups'], 2)
        self.assertTrue(all(c['legacy'] == c['unified'] == 'unavailable' for c in inventory['cases']))
        self.assertIsNone(inventory['unique_claims'])
        self.assertEqual(inventory['promoted'], 0)

    def test_design_packet_and_source_drift_rejected(self):
        revision = self.save()
        self.path.write_text(self.path.read_text() + ' ')
        with self.assertRaises(Rejected):
            load_prepared_cases(self.path, revision)
        revision = self.save()
        self.source.write_text('Changed synthetic source')
        with self.assertRaises(Rejected):
            load_prepared_cases(self.path, revision)

    def test_case_query_status_count_and_origin_drift_rejected(self):
        original = copy.deepcopy(self.design)
        for change in ['query', 'status', 'count', 'origin', 'promotion', 'unique']:
            self.design = copy.deepcopy(original)
            if change == 'query': self.design['cases'][0]['query'] = 'changed'
            if change == 'status': self.design['cases'][0]['retained_status'] = 'public-confirmed'
            if change == 'count': self.design['cases'].pop()
            if change == 'origin':
                for case in self.design['cases']: case['originating_evidence_group'] = 'one'
            if change == 'promotion': self.design['promoted'] = 1
            if change == 'unique': self.design['unique_claims'] = 19
            revision = self.save()
            with self.assertRaises(Rejected):
                load_prepared_cases(self.path, revision)


if __name__ == '__main__':
    unittest.main()
