"""Contract tests: fake protocol peer and injected Node lease, never native runtime."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import mock_open, patch

from unification.native_client import NativeClient, INVALID
from unification.partition import materialize_public
from unification.policy import AccessContext
from unification.registry import load_registry
from unification.service import MemoryService

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT/'unification/native_adapter.mjs'
STUB = Path(__file__).with_name('fake_native_child.py')


class NativeClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root/'sources'
        source.mkdir()
        self.source = source/'sample.md'
        self.source.write_text('Heading\nPublic cobalt wren.\nSecond public line.\n')
        self.revision = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.payload = {'version':2,'coverage':'partial','sources':[{'namespace':'wiki','root':str(source),'domain':'campaign',
            'approvals':[{'path':'sample.md','revision':self.revision,'sections':[{
                'section_id':'public','start_line':2,'end_line':3,'visibility':'public',
                'status':'provisional','authority':'campaign-record'}]}]}]}
        self.registry_path = self.root/'registry.json'
        self.save_registry()
        self.partition = self.root/'partition'
        self.manifest = materialize_public(load_registry(self.registry_path),self.partition)
        self.doc_id = 'wiki/sample.md#public'
        self.config = {'agents':{'defaults':{'workspace':str(self.partition/'workspace')},'entries':{
            'pilot':{'agentDir':str(self.partition/'state/agents/pilot/agent')}}},'memory':{'search':{
            'sources':['memory'],'rememberAcrossConversations':False,'experimental':{'sessionMemory':False},
            'extraPaths':[],'provider':'openai-compatible','fallback':'none','remote':{'baseUrl':'http://127.0.0.1:52182/v1'}}}}
        (self.partition/'openclaw.json').write_text(json.dumps(self.config))
        self.ctx = AccessContext()
        self.fixture_path = self.root/'peer.json'
        self.log = self.root/'requests.jsonl'

    def save_registry(self):
        self.registry_path.write_text(json.dumps(self.payload))

    def client(self, **fixture):
        self.fixture_path.write_text(json.dumps({'log':str(self.log),**fixture}))
        client = NativeClient(self.registry_path,self.partition,
            command=[sys.executable,str(STUB),str(self.fixture_path)],timeout=0.2)
        self.addCleanup(client.close)
        return client

    def requests(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def node(self, body, expected_exit=0):
        # All Node tests import only our module and inject a non-native provider.
        script = '''
import fs from 'node:fs/promises';
import {Readable, Writable} from 'node:stream';
import {NativeAdapter, openAdapter, assertConfig, assertPin, REVISION, serve} from __MODULE__;
const root = __ROOT__;
const registry = __REGISTRY__;
const manifest = __MANIFEST__;
const cfg = __CONFIG__;
const env = {OPENCLAW_STATE_DIR:root+'/state',OPENCLAW_CONFIG_PATH:root+'/openclaw.json'};
Object.assign(process.env,env);
for (const k of Object.keys(process.env)) if (k.startsWith('OPENCLAW_') && !(k in env)) delete process.env[k];
let searches=0, gets=0, validations=0, closes=0, managers=0, revokes=0, imports=0, leases=0;
let page={hits:[]};
let got={status:'ok',from:1,lines:1,text:'Public cobalt wren.\\n\\n[continuation notice]'};
const provider={search:async req=>{searches++;return page;},get:async req=>{gets++;return got;},
  health:async()=>({status:'ready'}),close:async()=>{closes++;}};
const make=()=>new NativeAdapter({provider,providerId:'fake',cfg,root,manifest,
  validateGeneration:async()=>{validations++;},revoke:()=>{revokes++;},closeManagers:async()=>{managers++;}});
const deps={readRevision:()=>REVISION,validateGeneration:async()=>{validations++;},loadFacade:async()=>{
  imports++;return {getActiveMemoryProvider:async()=>{leases++;return {provider,providerId:'fake'};},
  closeActiveMemorySearchManagers:async()=>{managers++;}};}};
BODY
'''
        for key, value in [('MODULE',NODE.as_uri()),('ROOT',str(self.partition)),('REGISTRY',str(self.registry_path)),
                           ('MANIFEST',self.manifest),('CONFIG',self.config)]:
            script = script.replace('__'+key+'__',json.dumps(value))
        script = script.replace('BODY',body)
        run = subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,expected_exit,run.stderr)
        if expected_exit:
            self.assertIn('private-local runtime revision mismatch',run.stderr)
            self.assertEqual(run.stdout,'')
            return {'exit_code':run.returncode}
        return json.loads(run.stdout)

    def test_pin_gate_precedes_facade_import_and_lease(self):
        result = self.node("""
let refused=false;
try {await openAdapter(root,registry,{...deps,readRevision:()=> 'wrong'});} catch {refused=true;}
console.log(JSON.stringify({refused,imports,leases,revision:REVISION}));
""")
        self.assertEqual(result,{'refused':True,'imports':0,'leases':0,'revision':'4d94a9fac61f2e83331a09df18ad35cdfb1faf5c'})
        # An uncaught startup refusal is nonzero, still using only injected peers.
        refused=self.node("await openAdapter(root,registry,{...deps,readRevision:()=> 'wrong'});",expected_exit=1)
        self.assertEqual(refused['exit_code'],1)

    def test_config_gate_all_unsafe_variants_refuse_before_import(self):
        result = self.node("""
const mutations=[c=>c.agents.defaults.workspace='/outside',c=>c.agents.entries.pilot.agentDir='/outside',
c=>c.agents.entries.pilot.workspace='/outside',c=>c.memory.search.sources=['memory','sessions'],
c=>c.memory.search.rememberAcrossConversations=true,c=>c.memory.search.experimental.sessionMemory=true,
c=>c.memory.search.extraPaths=['/outside'],c=>delete c.memory.search.extraPaths,
c=>c.memory.search.remote.baseUrl='https://example.invalid',c=>c.memory.search.provider='local',
c=>c.memory.search.fallback='local',c=>c.models={},c=>c.models=null,
c=>c.memory.search.remote.baseUrl='http://name:password@127.0.0.1:52182/v1'];
const refused=[];
for (const mutate of mutations) {
 const changed=structuredClone(cfg);mutate(changed);await fs.writeFile(root+'/openclaw.json',JSON.stringify(changed));
 try {await openAdapter(root,registry,deps);refused.push(false);} catch {refused.push(true);}
}
await fs.writeFile(root+'/openclaw.json',JSON.stringify(cfg));
for (const bad of [{...env,OPENCLAW_OTHER:'bad'},{...env,OPENCLAW_STATE_DIR:'/outside'}]) {
 try {assertConfig(cfg,root,bad);refused.push(false);} catch {refused.push(true);}
}
console.log(JSON.stringify({refused,imports,leases}));
""")
        self.assertEqual(result,{'refused':[True]*16,'imports':0,'leases':0})

    def test_minimum_score_allowlist_and_authoritative_provisional_citations(self):
        result = self.node("""
const reference={id:manifest.records[0].path};
page={hits:[{reference,score:0.2},{reference,score:NaN},{reference},
 {reference:{id:'memory/outside.md'},score:1},{reference,score:0.8,snippet:'Public cobalt wren.',automaticRecall:true}]};
const response=await make().dispatch({id:1,verb:'search',query:'wren',minScore:0.5,maxResults:3});
console.log(JSON.stringify({response,searches,validations}));
""")
        response = result['response']
        self.assertEqual(len(response['results']),1)
        hit = response['results'][0]
        self.assertEqual(hit['score'],0.8)
        self.assertEqual(response['dropped_outside_partition'],1)
        self.assertEqual(hit['doc_id'],self.doc_id)
        self.assertEqual(hit['reference']['id'],self.doc_id)
        self.assertEqual(hit['citation']['doc_id'],self.doc_id)
        self.assertEqual(hit['citation']['revision'],self.revision)
        self.assertEqual((hit['source_start_line'],hit['source_end_line']),(2,3))
        self.assertEqual(hit['claim_status'],'provisional')
        self.assertEqual(hit['authority'],'campaign-record')
        self.assertNotIn('automaticRecall',hit)
        self.assertEqual(response['status'],'ok')
        self.assertEqual(response['coverage'],'partial')
        self.assertEqual((result['searches'],result['validations']),(1,2))

    def test_bounded_get_validates_prefix_bounds_and_revision(self):
        result = self.node("""
const a=make(), req={id:1,verb:'get',doc_id:manifest.records[0].evidence.doc_id,from:1,lines:1};
const good=await a.dispatch(req);
const optional=await a.dispatch({...req,revision:null});
const invalid=[];
for(const change of [{from:0},{lines:0},{lines:201},{from:1.5}]) invalid.push(await a.dispatch({...req,...change}));
got={...got,text:'wrong prefix'};
const prefix=await a.dispatch(req);
got={...got,text:'Public cobalt wren.',lines:2};
const count=await a.dispatch(req);
const stale=await a.dispatch({...req,revision:'old'});
const denied=await a.dispatch({...req,doc_id:'../outside'});
console.log(JSON.stringify({good,optional,invalid,prefix,count,stale,denied,gets}));
""")
        self.assertEqual(result['good']['text'],'Public cobalt wren.')
        self.assertEqual(result['good']['source_line'],2)
        self.assertEqual(result['good']['lines_returned'],1)
        self.assertTrue(all(r['ok'] is False for r in result['invalid']))
        self.assertEqual(result['prefix']['status'],'unavailable')
        self.assertEqual(result['count']['status'],'unavailable')
        self.assertEqual(result['stale']['status'],'stale')
        self.assertEqual(result['denied']['status'],'denied')
        self.assertEqual(result['optional']['status'],'ok')
        self.assertEqual(result['gets'],4)

    def test_node_generation_checks_both_sides_search_and_get(self):
        result = self.node("""
const responses=[],calls=[];
for(const verb of ['search','get']) for(const failAt of [1,2]) {
 const a=make();let n=0;
 a.validateGeneration=async()=>{if(++n===failAt)throw Error('drift');};
 responses.push(await a.dispatch({id:1,verb,query:'wren',doc_id:manifest.records[0].evidence.doc_id,from:1,lines:1}));
 calls.push(n);
}
console.log(JSON.stringify({responses,calls,searches,gets}));
""")
        self.assertEqual(result['calls'],[1,2,1,2])
        self.assertEqual((result['searches'],result['gets']),(1,1))
        for response in result['responses']:
            self.assertEqual(response['status'],'unavailable')
            self.assertEqual(response['reason'],INVALID)
            self.assertEqual(response['results'],[])
            self.assertNotIn('text',response)

    def test_node_malformed_oversized_requests_and_budgets_keep_child_alive(self):
        result = self.node("""
const a=make();let output='';
const requests=['not json','x'.repeat(70000),JSON.stringify({id:1,verb:'unknown'}),
 JSON.stringify({id:2,verb:'search',query:'x'.repeat(4001)}),
 JSON.stringify({id:3,verb:'search',query:'x',maxResults:31}),
 JSON.stringify({id:4,verb:'search',query:'x',minScore:-1}),
 'null','[]','1','{}',JSON.stringify({id:5,verb:'ping'}),JSON.stringify({id:6,verb:'shutdown'})];
await serve(a,Readable.from([Buffer.from(requests.join('\\n')+'\\n')]),
 new Writable({write(chunk,encoding,callback){output+=chunk;callback();}}));
console.log(JSON.stringify({responses:output.trim().split('\\n').map(JSON.parse),searches,closes,managers,revokes}));
""")
        self.assertEqual(len(result['responses']),12)
        self.assertTrue(all(not r['ok'] for r in result['responses'][:10]))
        self.assertEqual(result['responses'][10]['status'],'ok')
        self.assertEqual(result['responses'][11]['status'],'closed')
        self.assertEqual((result['searches'],result['closes'],result['managers'],result['revokes']),(0,1,1,1))

    def test_node_shutdown_eof_and_closed_lease_reject_cached_reads(self):
        result = self.node("""
const a=make();await a.close();await a.close();
const after=await a.dispatch({id:1,verb:'search',query:'wren'});
const b=make();await serve(b,Readable.from([]),new Writable({write(c,e,cb){cb();}}));
console.log(JSON.stringify({after,closes,managers,revokes,searches}));
""")
        self.assertEqual(result['after']['status'],'unavailable')
        self.assertEqual((result['closes'],result['managers'],result['revokes'],result['searches']),(2,2,2,0))

    def test_client_protocol_ids_environment_isolation_and_service_hybrid(self):
        client = self.client()
        with patch.dict(os.environ,{'OPENCLAW_UNSAFE':'must not inherit'}), patch(
                'unification.native_client.subprocess.Popen',wraps=subprocess.Popen) as popen:
            result = MemoryService(load_registry(self.registry_path),client).search('wren',self.ctx,mode='hybrid')
        self.assertEqual(result['status'],'empty')
        self.assertEqual(result['backends'][0]['status'],'ready')
        env = popen.call_args.kwargs['env']
        self.assertEqual({k:v for k,v in env.items() if k.startswith('OPENCLAW_')},{
            'OPENCLAW_STATE_DIR':str(self.partition/'state'),'OPENCLAW_CONFIG_PATH':str(self.partition/'openclaw.json')})
        self.assertEqual(client.ping(self.ctx)['status'],'ok')
        ids = [r['id'] for r in self.requests() if 'id' in r]
        self.assertEqual(ids,list(range(1,len(ids)+1)))
        self.assertEqual([r['verb'] for r in self.requests() if 'verb' in r],['hello','search','ping'])

    def test_client_empty_unavailable_stale_and_honest_coverage(self):
        client = self.client()
        self.assertEqual(client.search('wren',self.ctx)['status'],'empty')
        client.revoke()
        self.assertEqual(client.search('wren',self.ctx)['status'],'stale')
        other = self.client(die=True)
        response = other.search('wren',self.ctx)
        self.assertEqual(response['status'],'unavailable')
        self.assertEqual(response['coverage'],'partial')
        third = self.client(response={'status':'unavailable','results':[],
            'coverage':'complete','backends':[{'id':'openclaw','status':'unavailable'}]})
        self.assertEqual(third.search('wren',self.ctx)['coverage'],'partial')
        fourth = self.client(response={'status':'empty','results':[],
            'coverage':'complete','backends':[{'id':'openclaw','status':'unavailable'}]})
        self.assertEqual(fourth.search('wren',self.ctx)['status'],'unavailable')

    def test_client_reloads_registry_before_and_after_every_search_and_get(self):
        client = self.client()
        with patch('unification.native_client.load_registry',wraps=load_registry) as loader, patch(
                'unification.native_client.validate_public',wraps=__import__('unification.partition',fromlist=['validate_public']).validate_public) as validator:
            client.search('wren',self.ctx)
            client.get(self.doc_id,self.ctx,lines=1)
        self.assertEqual(loader.call_count,4)
        self.assertEqual(validator.call_count,4)
        self.assertTrue(all(call.args[0] == self.registry_path for call in loader.call_args_list))
        self.assertIsNot(validator.call_args_list[0].args[0],validator.call_args_list[1].args[0])

    def test_generation_edits_revocations_reclassification_coverage_and_inputs_fail_closed(self):
        original = self.source.read_bytes()
        original_registry = copy.deepcopy(self.payload)
        projection = self.partition/'workspace'/self.manifest['records'][0]['path']
        projected = projection.read_bytes()
        mutations = ['source','revocation','classification','range','coverage','projection','USER.md','MEMORY.md','unexpected.md']
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.payload = copy.deepcopy(original_registry)
                self.source.write_bytes(original)
                projection.write_bytes(projected)
                for name in ('USER.md','MEMORY.md','unexpected.md'):
                    (self.partition/'workspace'/name).unlink(missing_ok=True)
                if mutation == 'source': self.source.write_text('changed')
                if mutation == 'revocation': self.payload['sources'][0]['approvals']=[]
                if mutation == 'classification': self.payload['sources'][0]['approvals'][0]['sections'][0]['visibility']='operator'
                if mutation == 'range': self.payload['sources'][0]['approvals'][0]['sections'][0]['start_line']=1
                if mutation == 'coverage': self.payload['coverage']='complete'
                if mutation == 'projection': projection.write_text('changed')
                if mutation.endswith('.md'): (self.partition/'workspace'/mutation).write_text('unexpected')
                self.save_registry()
                client = self.client()
                result = client.search('wren',self.ctx)
                self.assertEqual(result['status'],'unavailable')
                self.assertEqual(result['reason'],INVALID)
                self.assertIsNone(client.process)

    def test_after_io_source_and_registry_drift_discards_reply(self):
        for target in (self.source,self.registry_path):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                client = self.client(mutate=str(target))
                result = client.search('wren',self.ctx)
                self.assertEqual(result['status'],'unavailable')
                self.assertEqual(result['reason'],INVALID)
                self.assertEqual(result['results'],[])
                client.close()
                target.write_bytes(original)

    def test_timeout_two_consecutive_kill_restart_once_then_unavailable(self):
        for fixture in ({'hang':True},{'hello_hang':True}):
            with self.subTest(fixture=fixture):
                self.log.unlink(missing_ok=True)
                client = self.client(**fixture)
                started = time.monotonic()
                for unused in range(4):
                    self.assertEqual(client.search('wren',self.ctx)['status'],'unavailable')
                self.assertLess(time.monotonic()-started,3)
                self.assertEqual(client.restarts,1)
                self.assertEqual(sum(r.get('started',False) for r in self.requests()),2)
                self.assertIsNotNone(client.process.poll())
                before = len(self.requests())
                self.assertEqual(client.search('wren',self.ctx)['status'],'unavailable')
                self.assertEqual(len(self.requests()),before)
                client.close()

    def test_late_reply_cannot_answer_later_request_and_success_resets_timeout(self):
        client = self.client(delay_once=0.3)
        self.assertEqual(client.search('first',self.ctx)['status'],'unavailable')
        second=client.search('second',self.ctx)
        self.assertEqual(second['status'],'empty')
        self.assertEqual(second['query'],'second')
        self.assertEqual(client._timeouts,0)
        self.assertEqual(client.restarts,0)
        self.assertEqual([r['query'] for r in self.requests() if r.get('verb')=='search'],['first','second'])

    def test_revocation_during_io_and_next_call_fail_without_cached_results(self):
        client = self.client(delay_once=0.05)
        checks = []
        def check():
            checks.append(True)
            if len(checks)>1:
                raise RuntimeError('host revoked')
        ctx = AccessContext(assert_current=check)
        self.assertEqual(client.search('wren',ctx)['status'],'stale')
        self.assertIsNotNone(client.process.poll())
        before = len(self.requests())
        self.assertEqual(client.search('wren',self.ctx)['status'],'stale')
        self.assertEqual(len(self.requests()),before)

    def test_teardown_shutdown_reaps_child_and_close_is_idempotent(self):
        client = self.client()
        client.search('wren',self.ctx)
        process = client.process
        client.close();client.close()
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed and process.stdout.closed)
        self.assertEqual(self.requests()[-1]['verb'],'shutdown')
        self.assertEqual(client.search('wren',self.ctx)['status'],'unavailable')

    def test_startup_refusal_no_restart_or_live_fallback(self):
        client = self.client(startup_refusal=True)
        self.assertEqual(client.search('wren',self.ctx)['status'],'unavailable')
        self.assertEqual(client.search('wren',self.ctx)['status'],'unavailable')
        self.assertEqual(client.restarts,0)
        self.assertEqual(sum(r.get('started',False) for r in self.requests()),1)
        self.assertIsNotNone(client.process.poll())

    def test_client_budgets_and_inflight_cap(self):
        client = self.client()
        for query,limit in [('',1),('x'*4001,1),('x',31),('x',0),('x',True)]:
            with self.assertRaises(ValueError):client.search(query,self.ctx,limit)
        for start,lines in [(0,1),(1,0),(1,201),(True,1)]:
            with self.assertRaises(ValueError):client.get(self.doc_id,self.ctx,start_line=start,lines=lines)
        self.assertIsNone(client.process)
        client._lock.acquire()
        try:
            result = client.search('wren',self.ctx)
        finally:
            client._lock.release()
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['reason'],'request already in flight')
        self.assertIsNone(client.process)
        self.assertEqual(NativeClient.__init__.__kwdefaults__['timeout'],20.0)
        with self.assertRaises(ValueError): NativeClient(self.registry_path,self.partition,timeout=21)


    def test_node_single_caller_bound_lease_revocation_and_backend_coverage(self):
        result = self.node("""
let bound;
const injected={...deps,loadFacade:async()=>{imports++;return {
 getActiveMemoryProvider:async args=>{leases++;bound=args;
 return {provider:{...provider,search:async req=>{args.context.assertCurrent();return provider.search(req);}},providerId:'fake'};},
 closeActiveMemorySearchManagers:async()=>{managers++;}};}};
const a=await openAdapter(root,registry,injected);
page={hits:[],coverage:'partial'};a.manifest={...manifest,coverage:'complete'};
const first=await a.dispatch({id:1,verb:'search',query:'wren'});
const second=await a.dispatch({id:2,verb:'search',query:'wren'});
a.revoke();
const revoked=await a.dispatch({id:3,verb:'search',query:'wren'});
await a.close();
console.log(JSON.stringify({first,second,revoked,leases,imports,closes,managers,
 agentId:bound.agentId,purpose:bound.purpose,authority:bound.context.authority}));
""")
        self.assertEqual((result['leases'],result['imports'],result['closes'],result['managers']),(1,1,1,1))
        self.assertEqual(result['agentId'],'pilot')
        self.assertEqual(result['purpose'],'cli')
        self.assertEqual(result['authority'],{'kind':'operator','scopes':['operator.read']})
        self.assertEqual(result['first']['coverage'],'partial')
        self.assertEqual(result['second']['status'],'empty')
        self.assertEqual(result['revoked']['status'],'unavailable')

    def test_shadow_pairs_queries_and_records_revision_latency_and_separate_grades(self):
        from scripts.memory_unification_shadow import evaluate, pinned_cases, digest
        owner = self
        class Reader:
            def __init__(self, answer=False):self.calls=[];self.answer=answer
            def fingerprint(self):
                return {'corpus_sha256':digest([owner.doc_id]),'revisions_sha256':digest([owner.revision]),
                        'measurement_scope':'synthetic-fixture'}
            def run(self,case,ctx):
                self.calls.append((case,ctx))
                # Only one pinned case has this synthetic admitted reference.
                hit={**owner.manifest['records'][0]['evidence'],'doc_id':case.get('expected_doc','missing')+'#public'}
                response={'status':'ok','results':[hit],'coverage':'partial','backends':[{'id':'fake','status':'ready'}]}
                if self.answer:response['answer_review']={'status':'incorrect','reviewer':'fixture-review',
                                                         'rubric_revision':digest('fixture rubric')}
                return response
        legacy,unified=Reader(),Reader(True)
        ticks=iter(i/10 for i in range(1000))
        report=evaluate(legacy,unified,registry_path=self.registry_path,partition=self.partition,repeats=3,
                        clock=lambda:next(ticks))
        cases=pinned_cases()
        self.assertEqual(len(report['cases']),len(cases))
        self.assertEqual(len(legacy.calls),3*len(cases))
        self.assertEqual([c[0] for c in legacy.calls],[c[0] for c in unified.calls])
        self.assertTrue(all(a[1] is b[1] for a,b in zip(legacy.calls,unified.calls)))
        self.assertEqual([c[0]['query'] for c in legacy.calls],[c['query'] for c in cases for _ in range(3)])
        first=report['cases'][0]['backends']
        self.assertEqual(first['legacy']['runs'][0]['retrieval_correctness']['status'],'correct')
        self.assertEqual(first['legacy']['runs'][0]['answer_correctness']['status'],'not_assessed')
        self.assertEqual(first['unified']['runs'][0]['answer_correctness']['status'],'incorrect')
        self.assertEqual(first['legacy']['latency']['n'],3)
        self.assertEqual(first['legacy']['warm_latency']['n'],2)
        self.assertAlmostEqual(first['legacy']['latency']['p50_s'],0.1)
        self.assertAlmostEqual(first['legacy']['latency']['p95_s'],0.1)
        self.assertEqual(first['legacy']['target']['assessment'],'not_assessed')
        self.assertEqual(report['unique_facts_lost']['status'],'unavailable')
        self.assertEqual(report['fingerprints']['public_manifest_sha256'],hashlib.sha256(
            json.dumps(self.manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        from scripts.memory_unification_shadow import percentile_summary
        self.assertEqual(percentile_summary([0.9,0.1,0.2]),{'n':3,'p50_s':0.2,'p95_s':0.9})
        # Authoritative citation mapping; private/unreviewed refs cannot leak here.
        from scripts.memory_unification_shadow import ranked_evidence
        approved={(self.doc_id,self.revision):self.manifest['records'][0]['evidence']}
        rows=ranked_evidence({'results':[self.manifest['records'][0]['evidence'],{'doc_id':'not-reviewed','revision':'old','excerpt':'never saved'}]},approved)
        self.assertEqual(rows[0]['citation'],{'doc_id':self.doc_id,'revision':self.revision,
            'source_start_line':2,'source_end_line':3})
        self.assertTrue(rows[1]['redacted'])
        self.assertNotIn('not-reviewed',json.dumps(rows))
        self.assertNotIn('never saved',json.dumps(rows))

    def test_shadow_unique_fact_deduplication_and_no_evidence_text(self):
        from scripts.memory_unification_shadow import unique_facts_lost, digest
        def row(fact,group,public=False,legacy=True,unified=False):
            return {'fact_sha256':digest(fact),'evidence_group_sha256':digest(group),
                    'public':public,'legacy_retrievable':legacy,'unified_retrievable':unified}
        inventory={'reviewed':True,'records':[row('lost','group'),row('lost','group'),row('lost','another'),
            row('kept','group'),row('kept','group',public=True,unified=True),
            row('public miss','group',public=True),row('absent','group',legacy=False)]}
        report=unique_facts_lost(inventory)
        self.assertEqual(report['count'],1)
        self.assertEqual(report['reviewed_unique_facts'],4)
        self.assertEqual(report['unique_facts'][0]['fact_sha256'],digest('lost'))
        self.assertEqual(report['unique_facts'][0]['evidence_groups'],2)
        with self.assertRaises(ValueError):unique_facts_lost({'reviewed':False,'records':[]})
        inventory['records'][0]['text']='must not be accepted'
        with self.assertRaises(ValueError):unique_facts_lost(inventory)

    def test_shadow_unavailable_not_empty_targets_and_private_output(self):
        from scripts.memory_unification_shadow import evaluate, digest, write_report, OUTPUT_ROOT
        class Reader:
            def fingerprint(self):
                return {'corpus_sha256':digest('fixture corpus'),'revisions_sha256':digest(self.__class__.__name__),
                        'measurement_scope':'small-reviewed-partition'}
            def run(self,case,ctx):return {'status':'empty','results':[],'coverage':'complete',
                                          'backends':[{'id':'fake','status':'unavailable'}]}
        ticks=iter(range(1000))
        report=evaluate(Reader(),Reader(),registry_path=self.registry_path,partition=self.partition,
                        clock=lambda:next(ticks),repeats=2)
        observed=report['cases'][0]['backends']['legacy']
        self.assertEqual(observed['latency']['n'],0)
        self.assertEqual(observed['warm_latency']['p95_s'],None)
        self.assertEqual(observed['runs'][0]['status'],'unavailable')
        self.assertEqual(observed['runs'][0]['retrieval_correctness']['status'],'not_assessed')
        self.assertEqual(observed['target']['assessment'],'not_assessed')
        class Healthy(Reader):
            def run(self,case,ctx):return {'status':'empty','results':[],'coverage':'partial',
                                          'backends':[{'id':'fake','status':'ready'}]}
        healthy_ticks=iter(i*3 for i in range(1000))
        measured=evaluate(Healthy(),Healthy(),registry_path=self.registry_path,partition=self.partition,
                          clock=lambda:next(healthy_ticks),repeats=2)
        self.assertEqual(measured['cases'][0]['backends']['legacy']['target']['assessment'],'unmet')
        rules=next(c for c in measured['cases'] if c['id']=='rules-printed-page')
        self.assertEqual(rules['backends']['legacy']['target']['assessment'],'met')
        # Intercept exactly the filesystem call sites used by the collector. The
        # hermetic suite never writes real evaluation output or needs the volume.
        handle=mock_open()
        with patch('scripts.memory_unification_shadow.Path.mkdir') as mkdir, patch(
                'scripts.memory_unification_shadow.os.open',return_value=123) as opener, patch(
                'scripts.memory_unification_shadow.os.fdopen',handle):
            path=write_report({'synthetic_test':True,'cases':[]})
        self.assertEqual(path.parent.parent,Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification/shadow'))
        self.assertRegex(path.parent.name,r'^\d{8}T\d{12}Z$')
        self.assertEqual(opener.call_args.args[0],path)
        self.assertEqual(opener.call_args.args[2],0o600)
        self.assertEqual(mkdir.call_args.kwargs,{'parents':True,'exist_ok':False,'mode':0o700})
        written=''.join(c.args[0] for c in handle().write.call_args_list)
        self.assertEqual(json.loads(written),{'synthetic_test':True,'cases':[]})



    def test_node_real_python_validator_helper_reloads_authority_after_io(self):
        result=self.node("""
const a=await openAdapter(root,registry,{readRevision:deps.readRevision,loadFacade:deps.loadFacade});
const before=await a.dispatch({id:1,verb:'search',query:'wren'});
provider.search=async()=>{searches++;await fs.writeFile(registry,JSON.stringify({version:2,sources:[],coverage:'partial'}));return {hits:[]};};
const after=await a.dispatch({id:2,verb:'search',query:'wren'});
const next=await a.dispatch({id:3,verb:'search',query:'wren'});
await a.close();
console.log(JSON.stringify({before,after,next,searches}));
""")
        self.assertEqual(result['before']['status'],'empty')
        self.assertEqual(result['after']['status'],'unavailable')
        self.assertEqual(result['after']['reason'],INVALID)
        self.assertEqual(result['next']['status'],'unavailable')
        self.assertEqual(result['searches'],2)


if __name__ == '__main__':
    unittest.main()
