"""Regression tests for semantic-claim evidence, not line-based fact estimates."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.memory_unification_fact_review import (
    build_inventory, describe_source, load_fact_inventory, sha, summarize_claims,
    write_new_inventory,
)
from unification.partition import materialize_public
from unification.policy import AccessContext, StaleReference
from unification.service import MemoryService
from unification.registry import load_registry


class FactReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'mixed.md'
        self.source.write_text('# Known\nPublic emerald hamster.\n| Name | Value |\nGM secret violet otter.\n')
        self.registry_path = self.root/'registry.json'
        self.registry = {'version': 2, 'coverage': 'partial', 'sources': [{
            'namespace': 'wiki', 'root': str(self.root), 'domain': 'campaign', 'approvals': [{
                'path': 'mixed.md', 'revision': sha(self.source.read_bytes()), 'sections': [
                    {'section_id': 'known', 'start_line': 1, 'end_line': 3, 'visibility': 'public'},
                    {'section_id': 'secret', 'start_line': 4, 'end_line': 4, 'visibility': 'gm'}]}]}]}
        self.registry_path.write_text(json.dumps(self.registry))
        self.partition = self.root/'partition'
        materialize_public(load_registry(self.registry_path), self.partition)
        self.payload = build_inventory(registry_path=self.registry_path, partition=self.partition)
        self.path = self.root/'inventory.json'
        self.review = {'reviewer': 'test-reviewer', 'rubric_sha256': sha('semantic support rubric')}

    def load(self, payload=None):
        self.path.write_text(json.dumps(self.payload if payload is None else payload))
        return load_fact_inventory(self.path, registry_path=self.registry_path, partition=self.partition)

    def evidence(self, line):
        return {'doc_id': 'wiki/mixed.md', 'revision': sha(self.source.read_bytes()),
                'start_line': line, 'end_line': line,
                'passage_sha256': sha(self.source.read_text().splitlines()[line-1]),
                'origin_sha256': sha('original source')}

    def claim(self, line=2, name='one semantic proposition'):
        return {'claim_sha256': sha(name), 'canonical_query_sha256': sha('reviewed canonical query'),
                'review': {**self.review, 'unit_kind': 'semantic-claim'},
                'lineage': [self.evidence(line)], 'receipts': {'legacy': [], 'unified': []}}

    def receipt(self, claim, *, found=True, got='ok', support='supports', section=None):
        evidence = claim['lineage'][0]
        doc_id = evidence['doc_id'] + ('#'+section if section else '')
        query = {'query_sha256': claim['canonical_query_sha256'], 'status': 'ok' if found else 'empty',
                 'candidates': [{'doc_id': doc_id, 'revision': evidence['revision']}] if found else []}
        read = {'status': got, 'doc_id': doc_id, 'revision': evidence['revision'],
                'start_line': evidence['start_line'], 'end_line': evidence['end_line']}
        if got == 'ok':
            read['content_sha256'] = evidence['passage_sha256']
        receipt = {'query': query, 'get': read}
        if got == 'ok' and support:
            receipt['support_review'] = {**self.review, 'status': support}
        return receipt

    def complete(self):
        self.payload['review_scope'] = {**self.review, 'scope_sha256': sha('explicit reviewed scope'),
                                        'equivalent_evidence_complete': True}

    def test_headings_rows_lines_never_become_facts(self):
        descriptive = self.payload['descriptive_probe_inventory'][0]
        self.assertEqual(descriptive['headings'], 1)
        self.assertEqual(descriptive['table_rows'], 1)
        self.assertIsNone(descriptive['semantic_claim_count'])
        self.assertEqual(self.payload['claims'], [])
        result = summarize_claims(self.load())
        self.assertEqual(result['status'], 'not_assessed')
        self.assertIsNone(result['count'])
        self.assertIsNone(result['orphaned_fact_count'])

    def test_source_edit_rejects_inventory_even_when_unapproved(self):
        unapproved = self.root/'private.md'
        unapproved.write_text('A private fact.\n')
        payload = build_inventory(registry_path=self.registry_path, partition=self.partition,
                                  source_ids=['wiki/private.md'])
        unapproved.write_text('A changed private fact.\n')
        with self.assertRaises(StaleReference):
            self.load(payload)

    def test_registry_and_manifest_byte_generations_are_bound(self):
        self.registry_path.write_text(json.dumps(self.registry, indent=2))
        with self.assertRaises(StaleReference):
            self.load()
        self.registry_path.write_text(json.dumps(self.registry))
        manifest_path = self.partition/'partition.json'
        manifest_path.write_text(json.dumps(json.loads(manifest_path.read_text())))
        with self.assertRaises(StaleReference):
            self.load()

    def test_summarize_revalidates_previously_loaded_generation(self):
        loaded = self.load()
        self.source.write_text('Changed after loader\n')
        with self.assertRaises(StaleReference):
            summarize_claims(loaded)

    def test_candidate_only_is_unknown_not_fact_support(self):
        claim = self.claim()
        receipt = self.receipt(claim)
        receipt.pop('get'); receipt.pop('support_review')
        claim['receipts'] = {'legacy': [receipt], 'unified': [copy.deepcopy(receipt)]}
        self.payload['claims'] = [claim]
        self.complete()
        result = summarize_claims(self.load())
        self.assertEqual(result['claim_outcomes'][0]['legacy'], 'unknown')
        self.assertEqual(result['claim_outcomes'][0]['unified'], 'unknown')
        self.assertIsNone(result['count'])

    def test_bounded_get_without_passage_review_is_unknown(self):
        claim = self.claim()
        claim['receipts']['legacy'] = [self.receipt(claim, support=None)]
        claim['receipts']['unified'] = [self.receipt(claim, support=None, section='known')]
        self.payload['claims'] = [claim]
        result = summarize_claims(self.load())
        self.assertEqual(result['claim_outcomes'][0]['legacy'], 'unknown')

    def test_direct_get_after_query_miss_disproves_orphan(self):
        claim = self.claim()
        claim['receipts']['legacy'] = [self.receipt(claim, found=False)]
        claim['receipts']['unified'] = [self.receipt(claim, found=False, section='known')]
        self.payload['claims'] = [claim]
        self.complete()
        result = summarize_claims(self.load())
        self.assertEqual(result['claim_outcomes'][0]['legacy'], 'direct_read_support')
        self.assertEqual(result['claim_outcomes'][0]['probe_observations']['legacy'], ['ranking_miss'])
        self.assertEqual(result['claim_outcomes'][0]['unified'], 'direct_read_support')
        self.assertEqual(result['count'], 0)
        self.assertIsNone(result['orphaned_fact_count'])

    def test_duplicate_claims_and_derivative_lineage_deduplicate(self):
        claim = self.claim(4)
        claim['receipts']['legacy'] = [self.receipt(claim)]
        claim['receipts']['unified'] = [self.receipt(claim, found=False, got='denied', section='secret')]
        duplicate = copy.deepcopy(claim)
        duplicate['lineage'][0]['origin_sha256'] = sha('same fact, derivative source lineage')
        self.payload['claims'] = [claim, duplicate]
        self.complete()
        result = summarize_claims(self.load())
        self.assertEqual(result['status'], 'measured')
        self.assertEqual(result['reviewed_unique_claims'], 1)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['unique_facts'][0]['evidence_origins'], 2)

    def test_source_exclusion_without_read_denial_stays_unknown(self):
        claim = self.claim(4)
        claim['receipts']['legacy'] = [self.receipt(claim)]
        self.payload['claims'] = [claim]
        self.complete()
        result = summarize_claims(self.load())
        self.assertEqual(result['claim_outcomes'][0]['unified'], 'unknown')
        self.assertIsNone(result['count'])

    def test_public_ranking_miss_is_not_public_only_exclusion(self):
        claim = self.claim()
        claim['receipts']['legacy'] = [self.receipt(claim)]
        claim['receipts']['unified'] = [self.receipt(claim, found=False, got='denied', section='known')]
        self.payload['claims'] = [claim]
        self.complete()
        result = summarize_claims(self.load())
        self.assertEqual(result['claim_outcomes'][0]['unified'], 'unknown')
        self.assertIsNone(result['count'])

    def test_unreviewed_equivalent_lineage_cannot_be_claimed_complete_by_default(self):
        claim = self.claim(4)
        claim['receipts']['legacy'] = [self.receipt(claim)]
        claim['receipts']['unified'] = [self.receipt(claim, found=False, got='denied')]
        self.payload['claims'] = [claim]
        result = summarize_claims(self.load())
        self.assertIsNone(result['count'])
        self.assertEqual(result['unique_facts'], [])

    def test_false_passage_hash_and_nonsemantic_unit_rejected(self):
        claim = self.claim()
        self.payload['claims'] = [claim]
        claim['lineage'][0]['passage_sha256'] = sha('wrong passage')
        with self.assertRaises(StaleReference):
            self.load()
        claim['lineage'][0] = self.evidence(2)
        claim['review']['unit_kind'] = 'table-row'
        with self.assertRaises(ValueError):
            self.load()

    def test_canonical_query_and_read_receipts_must_match(self):
        claim = self.claim()
        claim['receipts']['legacy'] = [self.receipt(claim)]
        self.payload['claims'] = [claim]
        claim['receipts']['legacy'][0]['query']['query_sha256'] = sha('different query')
        with self.assertRaises(ValueError):
            self.load()
        claim['receipts']['legacy'][0] = self.receipt(claim)
        claim['receipts']['legacy'][0]['get']['content_sha256'] = sha('different read')
        with self.assertRaises(ValueError):
            self.load()

    def test_failed_read_cannot_supply_support_or_text(self):
        claim = self.claim()
        claim['receipts']['legacy'] = [self.receipt(claim, got='unavailable')]
        self.payload['claims'] = [claim]
        claim['receipts']['legacy'][0]['support_review'] = {**self.review, 'status': 'supports'}
        with self.assertRaises(ValueError):
            self.load()

    def test_raw_and_historical_inventory_never_trusted(self):
        with self.assertRaises(ValueError):
            summarize_claims(self.payload)
        with self.assertRaises(ValueError):
            self.load({'reviewer': 'cindylou-local-review', 'records': []})

    def test_new_write_cannot_overwrite_old_evidence(self):
        write_new_inventory(self.path, {'historical': True})
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_new_inventory(self.path, self.payload)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_unified_whole_mixed_page_alias_is_not_public_get_evidence(self):
        claim = self.claim()
        claim['receipts']['unified'] = [self.receipt(claim)]
        self.payload['claims'] = [claim]
        with self.assertRaises(ValueError):
            self.load()

    def test_bounded_receipts_larger_than_200_lines_rejected(self):
        source = self.root/'long.md'
        source.write_text('Repeated statement.\n' * 201)
        self.payload = build_inventory(registry_path=self.registry_path, partition=self.partition,
                                       source_ids=['wiki/long.md'])
        claim = self.claim()
        claim['lineage'] = [{'doc_id': 'wiki/long.md', 'revision': sha(source.read_bytes()),
                            'start_line': 1, 'end_line': 201,
                            'passage_sha256': sha(source.read_bytes()), 'origin_sha256': sha('long source')}]
        self.payload['claims'] = [claim]
        with self.assertRaises(ValueError):
            self.load()

    def test_passage_hash_matches_actual_memory_service_bounded_get(self):
        # Source has a final newline. The actual read does not: source-byte and
        # returned-passage hashes intentionally use different serializations.
        service = MemoryService(load_registry(self.registry_path))
        got = service.get('wiki/mixed.md#known', AccessContext(), start_line=2, lines=1)
        self.assertEqual(got['text'], 'Public emerald hamster.')
        self.assertNotEqual(sha(got['text']), sha('Public emerald hamster.\n'))
        claim = self.claim()
        receipt = self.receipt(claim, section='known')
        receipt['get']['content_sha256'] = sha(got['text'])
        self.assertEqual(claim['lineage'][0]['passage_sha256'], sha(got['text']))
        claim['receipts']['unified'] = [receipt]
        self.payload['claims'] = [claim]
        result = summarize_claims(self.load())
        self.assertEqual(result['claim_outcomes'][0]['unified'], 'query_and_read_support')

    def test_newline_serialization_normalizes_crlf_like_actual_bounded_get(self):
        # Exact source revision still changes, but returned text normalizes line
        # delimiters exactly like splitlines/join in the real shared read path.
        self.source.write_bytes(b'# Known\r\nPublic emerald hamster.\r\n| Name | Value |\r\nGM secret violet otter.\r\n')
        self.registry['sources'][0]['approvals'][0]['revision'] = sha(self.source.read_bytes())
        self.registry_path.write_text(json.dumps(self.registry))
        new_partition = self.root/'crlf-partition'
        materialize_public(load_registry(self.registry_path), new_partition)
        self.partition = new_partition
        self.payload = build_inventory(registry_path=self.registry_path, partition=self.partition)
        claim = self.claim()
        got = MemoryService(load_registry(self.registry_path)).get(
            'wiki/mixed.md#known', AccessContext(), start_line=2, lines=1)
        claim['receipts']['unified'] = [self.receipt(claim, section='known')]
        claim['receipts']['unified'][0]['get']['content_sha256'] = sha(got['text'])
        self.payload['claims'] = [claim]
        self.assertEqual(summarize_claims(self.load())['claim_outcomes'][0]['unified'], 'query_and_read_support')

    def test_inconsistent_query_statuses_and_duplicate_candidates_rejected(self):
        claim = self.claim()
        self.payload['claims'] = [claim]
        for status, candidates in [('ok', []), ('empty', [{'doc_id': 'wiki/mixed.md', 'revision': self.evidence(2)['revision']}])]:
            claim['receipts']['legacy'] = [{'query': {'query_sha256': claim['canonical_query_sha256'],
                                                     'status': status, 'candidates': candidates}}]
            with self.assertRaises(ValueError):
                self.load()
        receipt = self.receipt(claim)
        receipt['query']['candidates'].append(copy.deepcopy(receipt['query']['candidates'][0]))
        claim['receipts']['legacy'] = [receipt]
        with self.assertRaises(ValueError):
            self.load()

    def test_explicit_malformed_rank_stale_revision_and_boolean_bounds_rejected(self):
        claim = self.claim()
        self.payload['claims'] = [claim]
        receipt = self.receipt(claim)
        claim['receipts']['legacy'] = [receipt]
        receipt['query']['candidates'][0]['rank'] = -1
        with self.assertRaises(ValueError):
            self.load()
        del receipt['query']['candidates'][0]['rank']
        receipt['query']['candidates'][0]['revision'] = sha('old source generation')
        with self.assertRaises(StaleReference):
            self.load()
        receipt['query']['candidates'][0]['revision'] = self.evidence(2)['revision']
        receipt['get']['start_line'] = True
        with self.assertRaises(ValueError):
            self.load()

    def test_passage_longer_than_actual_character_bound_rejected(self):
        source = self.root/'longline.md'
        source.write_text('x' * 16001 + '\n')
        self.payload = build_inventory(registry_path=self.registry_path, partition=self.partition,
                                       source_ids=['wiki/longline.md'])
        claim = self.claim()
        claim['lineage'] = [{'doc_id': 'wiki/longline.md', 'revision': sha(source.read_bytes()),
                            'start_line': 1, 'end_line': 1,
                            'passage_sha256': sha('x' * 16001), 'origin_sha256': sha('long source')}]
        self.payload['claims'] = [claim]
        with self.assertRaises(ValueError):
            self.load()

    def test_wrong_authority_path_and_projection_mutation_fail_closed(self):
        path = self.partition/'workspace'/next((self.partition/'workspace/memory').iterdir()).relative_to(self.partition/'workspace')
        path.write_text('Unexpected index contents')
        with self.assertRaises(StaleReference):
            self.load()


if __name__ == '__main__':
    unittest.main()
