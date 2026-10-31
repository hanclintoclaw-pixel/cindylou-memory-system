#!/usr/bin/env python3
"""Controlled U2 repair verification. No cutover, source approval or live native CLI.

Private evidence contains query sets, opaque source-bound receipts and selected
before/after observations. This is not proof of historical/global non-mutation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from scripts.memory_unification_shadow import evaluate, write_report
from scripts.memory_unification_shadow_readers import CONTROL, LegacyReaders, UnifiedReader, content_snapshot
from scripts.memory_unification_fact_review import build_inventory, load_fact_inventory, sha, summarize_claims, write_new_inventory
from unification.native_client import NativeClient, validate_generation
from unification.policy import AccessContext


def observations(registry, partition):
    repos = {}
    for name in ('memory-system', 'campaign-wiki', 'discord_voice_patch'):
        path = (Path('/Users/hanclaw/claw/projects')/name if name == 'discord_voice_patch' else
                Path('/Users/hanclaw/claw/projects/cindylou')/name)
        values = []
        for args in (['rev-parse','HEAD'], ['status','--porcelain=v1'], ['diff','--binary'], ['diff','--cached','--binary']):
            r = subprocess.run(['git','-C',str(path),*args], capture_output=True, check=True)
            values.append(sha(r.stdout))
        repos[name] = values
    paths = [Path(registry), Path(partition)/'partition.json', Path.home()/'.openclaw/openclaw.json',
             Path('/Volumes/carbonite/claw/data/cindylou/cache/sr3data/pdf_page_text.json'),
             Path('/Volumes/carbonite/claw/data/cindylou/cache/sr3data/sr3data.sqlite')]
    files = []
    for path, revision in content_snapshot(paths):
        p = Path(path)
        files.append({'path':path, 'sha256':revision,
                      'mtime_ns':p.stat().st_mtime_ns if p.exists() else None})
    listener = subprocess.run(['lsof','-nP','-iTCP:52182','-sTCP:LISTEN','-Fpcn'],capture_output=True,check=True)
    return {'repositories':repos, 'selected_files':files, 'embedding_listener':listener.stdout.decode()}


def boundary(client, registry, manifest):
    ctx = AccessContext()
    record = manifest['records'][0]['evidence']
    source = next(s for s in registry.sources.values() if record['doc_id'].startswith(s.namespace+'/'))
    source_path = source.root/record['doc_id'].split('#')[0].split('/',1)[1]
    expected = source_path.read_text().splitlines()[record['source_start_line']]
    got = client.get(record['doc_id'],ctx,revision=record['revision'],start_line=2,lines=1)
    stale = client.get(record['doc_id'],ctx,revision='0'*64,start_line=1,lines=1)
    denied = client.get('wiki/PCs/Curtis.md',ctx,start_line=1,lines=1)
    rejected = False
    try:
        client.get(record['doc_id'],ctx,lines=201)
    except ValueError:
        rejected = True
    result = {'bounded_status':got['status'], 'source_line':got.get('source_line'),
              'expected_source_line':record['source_start_line']+1,
              'exact_prefix':got.get('text','').startswith(expected), 'stale_status':stale['status'],
              'unapproved_status':denied['status'], 'oversized_rejected':rejected}
    if not (got['status']=='ok' and result['source_line']==result['expected_source_line'] and
            result['exact_prefix'] and stale['status']=='stale' and denied['status']=='denied' and rejected):
        raise RuntimeError('native boundary verification failed')
    return result


def reviewed_claim_sample(legacy, unified, registry_path, partition, manifest):
    """Three explicit propositions, actual paired queries/reads; no global loss claim."""
    payload = build_inventory(registry_path=registry_path,partition=partition,
                              source_ids=['wiki/NPCs/Tom-Erlichman.md','wiki/PCs/Curtis.md'])
    review = {'reviewer':'openai/gpt-6.1-sol/high',
              'rubric_sha256':sha('Exact current asserted proposition in authoritative passage; bounded source read; no heading/table/count proxy; pending full equivalence review.')}
    definitions = [
        ('Tom Erlichman carried 250 nuyen on a certified credstick', 'wiki/NPCs/Tom-Erlichman.md',
         'Tom Erlichman credstick', ('Carried 250¥','certified credstick')),
        ('Curtis current tracked Karma Pool is 9', 'wiki/PCs/Curtis.md',
         'Curtis Karma Pool', ('Current tracked','Karma Pool: 9')),
        ('Curtis current tracked Good Karma is 25', 'wiki/PCs/Curtis.md',
         'Curtis Karma Pool', ('Current tracked','Karma): 25'))]
    for proposition, doc_id, query, terms in definitions:
        path = legacy._resolve(doc_id)
        source_lines = path.read_text().splitlines()
        number = next(i for i,line in enumerate(source_lines,1) if all(t in line for t in terms))
        source_text = source_lines[number-1]
        revision = legacy._file_revision(doc_id)
        evidence = {'doc_id':doc_id,'revision':revision,'start_line':number,'end_line':number,
                    'passage_sha256':sha(source_text),'origin_sha256':sha(doc_id)}
        claim = {'claim_sha256':sha(proposition),'canonical_query_sha256':sha(query),
                 'review':{**review,'unit_kind':'semantic-claim'},'lineage':[evidence],
                 'receipts':{'legacy':[],'unified':[]}}
        case = {'adapter':'campaign','query':query}
        for name, reader in (('legacy',legacy),('unified',unified)):
            result = reader.run(case,AccessContext())
            canonical = next((r['evidence'] for r in manifest['records']
                              if r['evidence']['doc_id'].split('#')[0]==doc_id and
                              r['evidence']['source_start_line'] <= number <= r['evidence']['source_end_line']),None)
            target_id = canonical['doc_id'] if name=='unified' and canonical else doc_id
            start = number-canonical['source_start_line']+1 if name=='unified' and canonical else number
            get_reader = reader._get_client() if name=='unified' else reader
            got = get_reader.get(target_id,AccessContext(),revision=revision,start_line=start,lines=1)
            # Native ranks chunks; claim receipts list distinct owning-source
            # identities in first-hit order, not multiple votes for one source.
            candidates = []
            seen = set()
            for hit in result['results']:
                identity = (hit['doc_id'],hit['revision'])
                if identity not in seen:
                    candidates.append({k:hit[k] for k in ('doc_id','revision')})
                    seen.add(identity)
            receipt = {'query':{'query_sha256':sha(query),'status':result['status'],
                               'candidates':candidates},
                       'get':{'status':got['status'],'doc_id':target_id,'revision':revision,
                              'start_line':number,'end_line':number}}
            if got['status']=='ok':
                # Native can append a continuation notice outside the source line.
                # It must start with the exact reviewed source; hash source only.
                if not got.get('text','').startswith(source_text):
                    raise RuntimeError('reviewed passage mismatch')
                if got.get('source_line') != number:
                    raise RuntimeError('reviewed source-line mismatch')
                receipt['get']['content_sha256'] = sha(got['text'][:len(source_text)])
                receipt['support_review'] = {**review,'status':'supports'}
            claim['receipts'][name].append(receipt)
        payload['claims'].append(claim)
    payload['review_scope'] = {**review,'scope_sha256':sha([c['claim_sha256'] for c in payload['claims']].__repr__()),
                               'equivalent_evidence_complete':False}
    return payload


def calibration(registry_path, partition):
    # Definitions retained verbatim; negatives include plausible questions about
    # real entity terms that the one-section partition cannot support.
    positives = ['Tom Erlichman','Tom Erlichman credstick','Tom Humanis informant',
                 'Sandusky security guard captured','Kurgan released Tom','250 certified credstick',
                 'private security personal capacity','Tom only survivor guard detail']
    nonsense = [f'Zzyzx-NoSuchCampaignEntity-{i}-quux' for i in range(94731,94741)]
    unsupported = ['Tom Erlichman favorite breakfast','Tom Erlichman childhood school',
                   'Tom Erlichman medical allergy','Tom Erlichman annual salary',
                   'Tom Erlichman middle name','Tom Erlichman birthday']
    client = NativeClient(registry_path,partition,min_score=0)
    rows = []
    try:
        for label,queries in [('content-related',positives),('nonsense',nonsense),('plausible-unsupported',unsupported)]:
            for query in queries:
                result = client.search(query,AccessContext(),5)
                if result['status'] not in {'ok','empty'}:
                    raise RuntimeError('calibration backend unavailable')
                scores = [h['score'] for h in result['results']]
                rows.append({'query':query,'label':label,'basis':'reviewed public section only',
                             'status':result['status'],'scores':scores,
                             'survives_0_30':any(s>=.30 for s in scores)})
    finally:
        process = client.process
        client.close()
    return {'rows':rows,'model_or_audio_included':False,'min_score_requested':0,
            'tested_floor':.30,'child_exit':process.returncode if process else None,
            'note':'Candidate scores only; not answer confidence, full-corpus calibration or threshold optimality.',
            'summary':{label:{'n':len([r for r in rows if r['label']==label]),
                              'surviving':sum(r['survives_0_30'] for r in rows if r['label']==label)}
                       for label in ('content-related','nonsense','plausible-unsupported')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--partition',type=Path,required=True)
    args = parser.parse_args()
    os.umask(0o077)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = CONTROL/'reviews'/stamp
    target.mkdir(mode=0o700,parents=True,exist_ok=False)
    manifest = json.loads((args.partition/'partition.json').read_bytes())
    registry = validate_generation(args.registry,args.partition,manifest)
    before = observations(args.registry,args.partition)
    legacy = LegacyReaders()
    unified = UnifiedReader(legacy,registry_path=args.registry,partition=args.partition)
    try:
        inventory_path = target/'reviewed-claims.private.json'
        write_new_inventory(inventory_path,reviewed_claim_sample(legacy,unified,args.registry,args.partition,manifest))
        inventory = load_fact_inventory(inventory_path,registry_path=args.registry,partition=args.partition)
        paired = evaluate(legacy,unified,registry_path=args.registry,partition=args.partition,repeats=3,fact_inventory=inventory)
        paired_path = write_report(paired)
        checks = boundary(unified._get_client(),registry,manifest)
        process = unified._client.process
    except Exception as error:
        failure = target/'failed-verification.private.json'
        write_new_inventory(failure, {'status':'failed','error_type':type(error).__name__,
            'reason':str(error),'before':before,'after':observations(args.registry,args.partition),
            'claim_inventory':str(target/'reviewed-claims.private.json'),
            'live_cutover':False})
        print(json.dumps({'failed_receipt':str(failure)}))
        raise
    finally:
        unified.close()
    checks['child_exit'] = process.returncode if process else None
    calibrated = calibration(args.registry,args.partition)
    validate_generation(args.registry,args.partition,manifest)
    after = observations(args.registry,args.partition)
    report = {'version':2,'model':'openai/gpt-6.1-sol','thinking':'high','live_cutover':False,
              'reviewed_code_sha256':sha(Path(__file__).read_bytes()),
              'paired_report':str(paired_path),'claim_inventory':str(inventory_path),
              'claim_summary':summarize_claims(inventory),'native_boundary':checks,
              'calibration':calibrated,'before':before,'after':after,
              'observed_surfaces_unchanged':before==after,
              'observation_limit':'Only these selected repositories/files/listener were observed; no historical/global non-mutation claim.'}
    output = target/'repair-verification.private.json'
    write_new_inventory(output,report)
    print(json.dumps({'report':str(output),'paired_report':str(paired_path),'cases':len(paired['cases']),
                      'observed_surfaces_unchanged':before==after,'native_boundary':checks,
                      'calibration':calibrated['summary'],'claims':report['claim_summary']}))


if __name__=='__main__':
    main()
