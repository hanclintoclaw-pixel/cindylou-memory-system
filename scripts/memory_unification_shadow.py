#!/usr/bin/env python3
"""Paired, default-off shadow collector. No implicit native/legacy process launches.

An explicitly injected local module exports create_adapters(args), returning
{'legacy': reader, 'unified': reader, 'fact_inventory': inventory_or_None}.
Each reader implements run(case, trusted_context) -> normalized result envelope
and fingerprint() -> {'corpus_sha256': ..., 'revisions_sha256': ...,
'measurement_scope': 'synthetic-fixture' | 'small-reviewed-partition' | 'full-corpus'}.
Readers must preserve the query/context, apply their own policy, and never manage
services. Missing fingerprints/reviews are reported unavailable, never fabricated.

Optional reviewed fact inventory is {'reviewed': True, 'records': [
 {'fact_sha256': SHA256, 'evidence_group_sha256': SHA256, 'public': bool,
  'legacy_retrievable': bool, 'unified_retrievable': bool}]}. No fact text is
accepted or saved. Hashes identify reviewed facts, not whole-document substitutes.
Final-answer grades require a separate answer_review with status, reviewer, and
rubric_revision (SHA256). Retrieval alone NEVER supplies an answer grade.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.memory_unification_eval import CONTROL
from unification.policy import AccessContext

OUTPUT_ROOT = CONTROL/'shadow'
CASES_PATH = ROOT/'docs/memory-unification/eval-cases.json'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def pinned_cases():
    # Same on-disk case set consumed by memory_unification_eval.py, not a copy.
    return json.loads(CASES_PATH.read_text())['cases']


def percentile_summary(values):
    ordered = sorted(values)
    return {'n':len(ordered),'p50_s':statistics.median(ordered) if ordered else None,
            'p95_s':ordered[math.ceil(.95*len(ordered))-1] if ordered else None}


def unique_facts_lost(inventory):
    if inventory is None:
        return {'status':'unavailable','count':None,'reason':'reviewed fact-level exclusion inventory not supplied'}
    if not isinstance(inventory,dict) or set(inventory) != {'reviewed','records'} or inventory['reviewed'] is not True:
        raise ValueError('reviewed fact-level inventory required')
    groups = {}
    for row in inventory['records']:
        if set(row) != {'fact_sha256','evidence_group_sha256','public','legacy_retrievable','unified_retrievable'} or any(
            not isinstance(row[k],str) or not SHA256.fullmatch(row[k]) for k in ('fact_sha256','evidence_group_sha256')) or any(
            type(row[k]) is not bool for k in ('public','legacy_retrievable','unified_retrievable')):
            raise ValueError('opaque fact/group hashes and explicit eligibility required; no evidence text')
        groups.setdefault(row['fact_sha256'],[]).append(row)
    lost = []
    for fact, rows in sorted(groups.items()):
        if any(r['unified_retrievable'] for r in rows):
            continue
        # A missing public fact is a retrieval regression, not public-only exclusion.
        if any(r['public'] for r in rows):
            continue
        if any(r['legacy_retrievable'] for r in rows):
            lost.append({'fact_sha256':fact,'evidence_groups':len({r['evidence_group_sha256'] for r in rows}),
                         'reason':'public-only exclusion'})
    return {'status':'measured','count':len(lost),'unique_facts':lost,
            'reviewed_unique_facts':len(groups),'note':'Fact identifiers only; no nonpublic evidence text.'}


def retrieval_check(case, response):
    hits = response.get('results',[])
    if not isinstance(hits,list):
        return {'status':'not_assessed','reason':'invalid results envelope'}
    if response.get('status') not in {'ok','empty'}:
        return {'status':'not_assessed','reason':'backend not available'}
    checks = {}
    if case.get('expected_doc'):
        checks['expected_doc_in_top5'] = any(h.get('doc_id','').split('#')[0] == case['expected_doc'] for h in hits[:5])
    if case.get('expected_empty'):
        checks['empty'] = not hits
    if case.get('expected_decline'):
        # This is specialist admission/decline evidence, not a generated-answer grade.
        checks['specialist_declined'] = response.get('accepted') is False
    if case.get('expected_name'):
        admitted = [h for h in hits if h.get('name','').casefold() == case['expected_name'].casefold()
                    and h.get('tier') in {'SR3','VERIFIED'}]
        checks['named_citable_candidate'] = bool(admitted)
        checks['citation_preserved'] = any(h.get('cite','').split(' -> ',1)[0] == case['expected_citation'] for h in admitted)
        checks['damage_exact'] = any(h.get('fields',{}).get('Damage') == case['expected_damage'] for h in admitted)
    return {'status':('correct' if all(checks.values()) else 'incorrect') if checks else 'not_assessed',
            'checks':checks,'note':'Retrieval/admission only; source-term presence is not an answer grade.'}


def answer_check(response):
    review = response.get('answer_review')
    if not isinstance(review,dict) or review.get('status') not in {'correct','incorrect'} or not isinstance(
            review.get('reviewer'),str) or not review['reviewer'] or not isinstance(review.get('rubric_revision'),str) or not SHA256.fullmatch(review['rubric_revision']):
        return {'status':'not_assessed','reason':'independent final-answer review not supplied'}
    return {k:review[k] for k in ('status','reviewer','rubric_revision')}


def ranked_evidence(response, approved):
    """No snippets or private evidence in the collector, even from legacy adapters."""
    references = []
    for rank, hit in enumerate(response.get('results',[]),1):
        doc_id, revision = hit.get('doc_id'), hit.get('revision')
        evidence = approved.get((doc_id,revision))
        if evidence is None:
            references.append({'rank':rank,'reference_sha256':digest([doc_id,revision]),
                               'redacted':True,'reason':'outside reviewed public generation'})
            continue
        # Reconstruct citations from reviewed authority, not an arbitrary provider string.
        references.append({'rank':rank,'doc_id':doc_id,'revision':revision,
            'claim_status':evidence['claim_status'],'authority':evidence['authority'],
            'citation':{'doc_id':doc_id,'revision':revision,
                'source_start_line':evidence['source_start_line'],'source_end_line':evidence['source_end_line']}})
    return references


def backend_fingerprint(reader):
    try:
        result = reader.fingerprint()
    except Exception:
        return {'status':'unavailable','reason':'adapter corpus/revision fingerprint unavailable'}
    if not isinstance(result,dict) or any(not isinstance(result.get(k),str) or not SHA256.fullmatch(result[k])
            for k in ('corpus_sha256','revisions_sha256')) or result.get('measurement_scope') not in {
                'synthetic-fixture','small-reviewed-partition','full-corpus'}:
        return {'status':'unavailable','reason':'invalid adapter fingerprint'}
    return {'status':'available',**{k:result[k] for k in ('corpus_sha256','revisions_sha256','measurement_scope')}}


def evaluate(legacy, unified, *, registry_path, partition, repeats=3, fact_inventory=None, clock=time.monotonic):
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError('repeats must be 1..10')
    # Reuse the same complete-generation boundary as the NativeReader.
    from unification.native_client import validate_generation
    manifest = json.loads((Path(partition)/'partition.json').read_text())
    registry = validate_generation(Path(registry_path),Path(partition),manifest)
    approved = {(r['evidence']['doc_id'],r['evidence']['revision']):r['evidence'] for r in manifest['records']}
    cases = pinned_cases()
    fingerprint = {'registry_sha256':hashlib.sha256(Path(registry_path).read_bytes()).hexdigest(),
        'public_manifest_sha256':digest(manifest),'case_set_sha256':hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        'corpus_sha256':digest(sorted(e[0] for e in approved)),
        'revisions_sha256':digest(sorted([list(e) for e in approved])),'coverage':registry.coverage}
    readers = {'legacy':legacy,'unified':unified}
    fingerprints = {name:backend_fingerprint(reader) for name,reader in readers.items()}
    report = {'version':1,'live_cutover':False,'fingerprints':fingerprint,'backend_fingerprints':fingerprints,
        'context':{'audience':'public','authority':'trusted local evaluation; not a session lease'},
        'timing_note':'Experimental paired retrieval timings, separate from model/audio. Small-corpus or synthetic runs are NOT full-wiki p95. With n=3 p95 is the sample maximum.',
        'unique_facts_lost':unique_facts_lost(fact_inventory),'cases':[]}
    context = AccessContext()
    for case in cases:
        row = {'id':case['id'],'query':case['query'],'adapter':case['adapter'],'backends':{}}
        runs = {name:[] for name in readers}
        # Exactly one call to each backend per pair; no retries or hidden fallback.
        for repeat in range(repeats):
            for name,reader in readers.items():
                before = clock()
                try:
                    response = reader.run(dict(case),context)
                    if not isinstance(response,dict) or response.get('status') not in {'ok','empty','stale','unavailable','denied'} or not isinstance(response.get('results'),list):
                        raise ValueError('normalized backend envelope required')
                    backends = response.get('backends')
                    if not isinstance(backends,list) or not backends or any(not isinstance(b,dict) for b in backends):
                        raise ValueError('explicit backend status required')
                    if response['status'] in {'ok','empty'} and any(b.get('status') != 'ready' for b in backends):
                        raise ValueError('unavailable is not a healthy empty search')
                    if response['status'] not in {'ok','empty'} or any(b.get('status') != 'ready' for b in backends):
                        response = {**response,'coverage':'partial'}
                except Exception as error:
                    response = {'status':'unavailable','results':[],'coverage':'partial',
                        'backends':[{'id':name,'status':'unavailable','reason':type(error).__name__}]}
                elapsed = clock()-before
                runs[name].append({'run':repeat,'elapsed_s':elapsed,'status':response['status'],
                    'backend_status':[{'id':b.get('id'),'status':b.get('status')} for b in response.get('backends',[])],
                    'coverage':response.get('coverage','partial'),
                    'ranked_references':ranked_evidence(response,approved),
                    'retrieval_correctness':retrieval_check(case,response),'answer_correctness':answer_check(response)})
        for name,observations in runs.items():
            healthy = [r['elapsed_s'] for r in observations if r['status'] in {'ok','empty'}]
            warm = [r['elapsed_s'] for r in observations[1:] if r['status'] in {'ok','empty'}]
            warm_stats = percentile_summary(warm)
            target = 4.5 if case['adapter']=='rules' else 2.0 if case['adapter'] in {'campaign','equipment'} else None
            measurable = (bool(warm) and target is not None and fingerprints[name].get('status')=='available'
                          and fingerprints[name].get('measurement_scope') != 'synthetic-fixture')
            row['backends'][name] = {'runs':observations,'latency':percentile_summary(healthy),'warm_latency':warm_stats,
                'attempted_n':len(observations),'cold_first_s':observations[0]['elapsed_s'],
                'corpus_revision_fingerprint':fingerprints[name],
                'target':{'p95_s':target,'assessment':('met' if warm_stats['p95_s']<=target else 'unmet') if measurable else 'not_assessed'}}
        report['cases'].append(row)
    # Corpus edits during an evaluation invalidate its evidence, too.
    validate_generation(Path(registry_path),Path(partition),manifest)
    return report


def write_report(report):
    # No --out escape hatch. Every on-disk result is private and UTC-Z dated.
    if OUTPUT_ROOT.is_symlink() or OUTPUT_ROOT.resolve() != OUTPUT_ROOT.absolute():
        raise ValueError('canonical private control root required')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = OUTPUT_ROOT/stamp
    target.mkdir(parents=True,exist_ok=False,mode=0o700)
    output = target/'shadow.private.json'
    fd = os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
        stream.write('\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter-file',type=Path,required=True,help='trusted local injection; never starts native implicitly')
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--partition',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    args = parser.parse_args()
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('shadow_injected_adapter',args.adapter_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    adapters = module.create_adapters(args)
    report = evaluate(adapters['legacy'],adapters['unified'],registry_path=args.registry,partition=args.partition,
        repeats=args.repeats,fact_inventory=adapters.get('fact_inventory'))
    output = write_report(report)
    print(json.dumps({'output':str(output),'cases':len(report['cases']),
        'note':'Injected shadow evidence only; no deployment or parity assertion.'}))


if __name__ == '__main__':
    main()
