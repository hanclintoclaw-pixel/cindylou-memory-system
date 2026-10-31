"""Counterexamples from the Sol review; no production or native runtime used."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import memory_unification_shadow as shadow
from scripts.memory_unification_shadow_readers import LegacyReaders, UnifiedReader, content_snapshot, passage_receipt
from unification.policy import AccessContext, StaleReference
from unification.partition import materialize_public
from unification.registry import load_registry


class ShadowEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'page.md'
        self.source.write_text('Heading\nFact cobalt wren.\n')
        self.revision = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.registry = self.root/'registry.json'
        self.registry.write_text(json.dumps({'version':2,'coverage':'partial','sources':[{
            'namespace':'wiki','root':str(self.root),'domain':'campaign','approvals':[{
                'path':'page.md','revision':self.revision,'sections':[{
                    'section_id':'known','start_line':2,'end_line':2,'visibility':'public',
                    'status':'provisional','authority':'campaign-record'}]}]}]}))
        self.partition = self.root/'partition'
        materialize_public(load_registry(self.registry), self.partition)

    def test_expected_document_without_fact_cannot_pass(self):
        case = {'expected_doc':'wiki/page.md','required_source_terms':['cobalt wren']}
        hit = {'doc_id':'wiki/page.md','revision':self.revision}
        response = {'status':'ok','results':[hit]}
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'incorrect')
        response['passage_evidence'] = [passage_receipt(case,hit,{'status':'ok','revision':self.revision,
            'text':'Not the fact','source_line':1,'lines_returned':1})]
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'incorrect')
        response['passage_evidence'] = [passage_receipt(case,hit,{'status':'ok','revision':self.revision,
            'text':'Fact cobalt wren.','source_line':2,'lines_returned':1})]
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'correct')
        response['passage_evidence'][0]['revision'] = '0'*64
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'incorrect')

    def test_rules_citation_without_support_or_admission_fails(self):
        case={'expected_rule_citation':'Core p.87','required_rule_terms':['Stealth (Quickness)']}
        hit={'doc_id':'rules/source.md','revision':self.revision,'citation':'Core p.87',
             'printed_page':87,'excerpt':'Stealth (Quickness)'}
        response={'status':'ok','accepted':True,'results':[hit]}
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'correct')
        hit['excerpt']='Aquatics and swimming'
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'incorrect')
        hit['excerpt']='Stealth (Quickness)'
        response['accepted']=False
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'incorrect')

    def test_equipment_fields_must_belong_to_same_admitted_candidate(self):
        case={'expected_name':'Pistol','expected_citation':'sr3.278','expected_damage':'9M'}
        hit={'name':'Pistol','tier':'VERIFIED','cite':'sr3.278','revision':self.revision,'fields':{'Damage':'1L'}}
        response={'status':'ok','results':[hit,{**hit,'cite':'sr3.999','fields':{'Damage':'9M'}}]}
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'incorrect')
        hit['fields']['Damage']='9M'
        self.assertEqual(shadow.retrieval_check(case,response)['status'],'correct')

    def test_namespace_and_revision_are_content_based_not_cached(self):
        legacy=LegacyReaders.__new__(LegacyReaders)
        legacy.memory_root=self.root/'memory'
        legacy.bridge=types.SimpleNamespace(CAMPAIGN_WIKI_ROOT=self.root,WORKSPACE_ROOT=self.root)
        self.assertEqual(legacy._file_revision('wiki/page.md'),self.revision)
        self.assertEqual(legacy._file_revision('workspace/page.md'),self.revision)
        before=content_snapshot([self.source])
        self.source.write_text('Other text of same path\n')
        self.assertNotEqual(legacy._file_revision('wiki/page.md'),self.revision)
        self.assertNotEqual(content_snapshot([self.source]),before)

    def test_operator_cli_is_never_launched(self):
        legacy=LegacyReaders.__new__(LegacyReaders)
        with patch('subprocess.run', side_effect=AssertionError('live process forbidden')):
            result=legacy.run({'adapter':'native-operator','query':'x'},AccessContext())
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['results'],[])

    def test_whole_page_not_blanket_approved_and_specialist_citations_retained(self):
        approved={('wiki/page.md#known',self.revision):{'doc_id':'wiki/page.md#known','source_start_line':2,
            'source_end_line':2,'claim_status':'provisional','authority':'campaign-record'}}
        rows=shadow.ranked_evidence({'results':[{'doc_id':'wiki/page.md','revision':self.revision}]},approved)
        self.assertNotIn('citation',rows[0])
        self.assertEqual(rows[0]['approved_sections'][0]['source_start_line'],2)
        source='00_sources/rules_references/core_rules/Book/source.md'
        snapshot={'generation_sha256':'0'*64,'backend_version':'1'*64,
                  'source_revisions':{'/data/'+source:self.revision}}
        response={'results':[{'doc_id':source,'revision':self.revision,'domain':'rules',
            'backend_version':'1'*64,'printed_page':87,'citation':'Core p.87','excerpt':'Never persist'}],
            'backends':[{'id':'rules-specialist-wrapped','status':'ready',**snapshot}]}
        rows=shadow.ranked_evidence(response,approved,adapter='rules',fingerprint={'specialists':{'rules':snapshot}})
        self.assertEqual(rows[0]['citation'],'Core p.87')
        self.assertNotIn('excerpt',rows[0])
        response['results'][0]['doc_id']='wiki/private-secret.md'
        rows=shadow.ranked_evidence(response,approved,adapter='rules',fingerprint={'specialists':{'rules':snapshot}})
        self.assertTrue(rows[0]['redacted'])
        self.assertNotIn('private-secret',json.dumps(rows))
        response['results'][0]['doc_id']=source
        rows=shadow.ranked_evidence(response,approved,adapter='campaign',fingerprint={'specialists':{'rules':snapshot}})
        self.assertTrue(rows[0]['redacted'])

    def test_supplied_registry_partition_bound_to_client(self):
        fake=types.SimpleNamespace(specialists=None)
        reader=UnifiedReader(fake,registry_path=self.registry,partition=self.partition,
            client_factory=lambda: 'sentinel')
        self.assertEqual(reader.registry_path,self.registry)
        self.assertEqual(reader.partition,self.partition)
        self.assertEqual(reader._get_client(),'sentinel')

    def test_generation_drift_rejects_entire_paired_report_and_warnings_not_empty(self):
        class Reader:
            def __init__(self,drift=False,warning=False):
                self.n=0;self.drift=drift;self.warning=warning
            def fingerprint(self):
                self.n+=1
                return {'corpus_sha256':('1' if self.drift and self.n>1 else '0')*64,
                        'revisions_sha256':'0'*64,'measurement_scope':'synthetic-fixture'}
            def run(self,case,ctx):
                return {'status':'empty','results':[],'backends':[{'id':'test','status':'ready'}],
                        'warning':'index stale' if self.warning else None}
        cases=[{'id':'empty','adapter':'campaign','query':'absent','expected_empty':True}]
        with patch.object(shadow,'pinned_cases',return_value=cases):
            with self.assertRaises(StaleReference):
                shadow.evaluate(Reader(drift=True),Reader(),registry_path=self.registry,partition=self.partition,repeats=2)
            report=shadow.evaluate(Reader(warning=True),Reader(),registry_path=self.registry,partition=self.partition,repeats=3)
        legacy=report['cases'][0]['backends']['legacy']
        self.assertEqual(legacy['runs'][0]['status'],'unavailable')
        self.assertEqual(legacy['runs'][0]['retrieval_correctness']['status'],'not_assessed')
        self.assertEqual(report['cases'][0]['backends']['unified']['warm_latency']['n'],2)

    def test_failed_warm_attempt_cannot_pass_latency_target(self):
        class Reader:
            def __init__(self): self.n=0
            def fingerprint(self):
                return {'corpus_sha256':'0'*64,'revisions_sha256':'0'*64,'measurement_scope':'small-reviewed-partition'}
            def run(self,case,ctx):
                self.n+=1
                return {'status':'unavailable' if self.n==2 else 'empty','results':[],
                        'backends':[{'id':'test','status':'unavailable' if self.n==2 else 'ready'}]}
        with patch.object(shadow,'pinned_cases',return_value=[{'id':'case','adapter':'campaign','query':'q'}]):
            report=shadow.evaluate(Reader(),Reader(),registry_path=self.registry,partition=self.partition,repeats=3)
        result=report['cases'][0]['backends']['unified']
        self.assertEqual(result['warm_latency']['n'],1)
        self.assertEqual(result['target']['assessment'],'not_assessed')

    def test_old_boolean_fact_inventory_rejected(self):
        with self.assertRaises(ValueError):
            shadow.unique_facts_lost({'reviewed':True,'records':[]})
