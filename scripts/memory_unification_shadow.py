#!/usr/bin/env python3
"""Paired, default-off shadow collector. No implicit native/legacy process launches.

An explicitly injected local module exports create_adapters(args), returning
{'legacy': reader, 'unified': reader, 'fact_inventory': inventory_or_None}.
Each reader implements run(case, trusted_context) -> normalized result envelope
and fingerprint() -> {'corpus_sha256': ..., 'revisions_sha256': ...,
'measurement_scope': 'synthetic-fixture' | 'small-reviewed-partition' | 'full-corpus'}.
Readers must preserve the query/context, apply their own policy, and never manage
services. Missing fingerprints/reviews are reported unavailable, never fabricated.

Optional schema-v2 claim inventory binds source revisions, semantic review and
query/bounded-read receipts. Old line/probe inventories cannot measure unique loss.
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
    from scripts.memory_unification_fact_review import summarize_claims
    if not isinstance(inventory, dict) or inventory.get('version') != 2:
        raise ValueError('revision-bound schema-v2 claim inventory required')
    return summarize_claims(inventory)


def retrieval_check(case, response):
    hits = response.get('results',[])
    if not isinstance(hits,list):
        return {'status':'not_assessed','reason':'invalid results envelope'}
    if response.get('status') not in {'ok','empty','decline'}:
        return {'status':'not_assessed','reason':'backend not available'}
    checks = {}
    if case.get('expected_doc'):
        checks['expected_doc_in_top5'] = any(h.get('doc_id','').split('#')[0] == case['expected_doc'] for h in hits[:5])
    if case.get('required_source_terms'):
        checks['bounded_fact_support'] = any(
            p.get('status') == 'ok' and p.get('doc_id','').split('#')[0] == case['expected_doc']
            and isinstance(p.get('revision'), str) and SHA256.fullmatch(p['revision'])
            and p.get('revision') == h.get('revision') and p.get('doc_id') == h.get('doc_id')
            and isinstance(p.get('source_line'), int) and p['source_line'] >= 1
            and type(p.get('lines_returned')) is int and 1 <= p['lines_returned'] <= 200
            and isinstance(p.get('passage_sha256'), str) and SHA256.fullmatch(p['passage_sha256'])
            and p.get('required_terms_sha256') == digest(case['required_source_terms'])
            and p.get('required_terms_present') == [True]*len(case['required_source_terms'])
            and p.get('supports_required_fact') is True
            for p in response.get('passage_evidence', []) for h in hits[:5])
    if case.get('expected_empty'):
        checks['empty'] = not hits
    if case.get('expected_decline'):
        # This is specialist admission/decline evidence, not a generated-answer grade.
        checks['specialist_declined'] = response.get('accepted') is False
    if case.get('expected_name'):
        admitted = [h for h in hits if h.get('name','').casefold() == case['expected_name'].casefold()
                    and h.get('tier') in {'SR3','VERIFIED'}]
        checks['named_citable_candidate'] = bool(admitted)
        checks['exact_evidence_same_candidate'] = any(h.get('cite','').split(' -> ',1)[0] == case['expected_citation']
            and h.get('fields',{}).get('Damage') == case['expected_damage']
            and isinstance(h.get('revision'),str) and SHA256.fullmatch(h['revision']) for h in admitted)
    if case.get('expected_rule_citation'):
        checks['specialist_accepted'] = response.get('accepted') is True
        checks['rule_passage_and_printed_citation'] = any(
            h.get('citation') == case['expected_rule_citation']
            and type(h.get('printed_page')) is int and h['printed_page'] > 0
            and isinstance(h.get('revision'),str) and SHA256.fullmatch(h['revision'])
            and all(t in h.get('excerpt','') for t in case['required_rule_terms']) for h in hits)
    return {'status':('correct' if all(checks.values()) else 'incorrect') if checks else 'not_assessed',
            'checks':checks,'note':'Retrieval/admission only; source-term presence is not an answer grade.'}


def answer_check(response):
    review = response.get('answer_review')
    if not isinstance(review,dict) or review.get('status') not in {'correct','incorrect'} or not isinstance(
            review.get('reviewer'),str) or not review['reviewer'] or not isinstance(review.get('rubric_revision'),str) or not SHA256.fullmatch(review['rubric_revision']):
        return {'status':'not_assessed','reason':'independent final-answer review not supplied'}
    return {k:review[k] for k in ('status','reviewer','rubric_revision')}


def specialist_evidence_bound(hit, response, adapter, fingerprint):
    """Domain labels are not grants; bind to the trusted pre-run source snapshot."""
    if adapter not in {'rules','equipment'} or hit.get('domain') != adapter:
        return False
    trusted = (fingerprint or {}).get('specialists', {}).get(adapter)
    if not isinstance(trusted,dict) or hit.get('backend_version') != trusted.get('backend_version'):
        return False
    if not any(b.get('id') == adapter+'-specialist-wrapped' and b.get('status') == 'ready'
               and all(b.get(k) == trusted.get(k) for k in ('generation_sha256','backend_version','source_revisions'))
               for b in response.get('backends',[])):
        return False
    doc_id, revision = hit.get('doc_id',''), hit.get('revision')
    if not isinstance(revision,str) or not SHA256.fullmatch(revision):
        return False
    sources = trusted.get('source_revisions',{})
    if adapter == 'equipment':
        return (doc_id.startswith('sr3data:') and hit.get('tier') in {'VERIFIED','SR3','WEAK'} and
                any(Path(path).name == 'sr3data.sqlite' and rev == revision for path,rev in sources.items()))
    return (doc_id.startswith('00_sources/rules_references/') and '..' not in Path(doc_id).parts and
            any(path.endswith('/'+doc_id) and rev == revision for path,rev in sources.items()))


def ranked_evidence(response, approved, *, adapter=None, fingerprint=None):
    """No snippets or private evidence in the collector, even from legacy adapters."""
    references = []
    for rank, hit in enumerate(response.get('results',[]),1):
        doc_id, revision = hit.get('doc_id'), hit.get('revision')
        # SR3 specialist citations have their own reviewed source/code revision;
        # they are not campaign registry grants. Never persist their excerpts.
        if specialist_evidence_bound(hit, response, adapter, fingerprint):
            references.append({'rank':rank, **{k:hit[k] for k in (
                'doc_id','revision','domain','citation','printed_page','marker_page',
                'cite','tier','name','source_revisions','backend_version') if k in hit}})
            continue
        evidence = approved.get((doc_id,revision))
        # Whole mixed legacy pages must not inherit a neighboring approved section.
        if evidence is None and '#' not in (doc_id or ''):
            matches = [v for (key,rev),v in approved.items() if key.split('#')[0] == doc_id and rev == revision]
            if matches:
                references.append({'rank':rank,'doc_id':doc_id,'revision':revision,
                    'scope':'approved-sections-only; other page content not authorized',
                    'approved_sections':[{k:v[k] for k in ('doc_id','source_start_line','source_end_line','claim_status','authority')} for v in matches]})
                continue
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
    return {'status':'available',**result}


def evaluate(legacy, unified, *, registry_path, partition, repeats=3, fact_inventory=None, clock=time.monotonic):
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError('repeats must be 1..10')
    # Reuse the same complete-generation boundary as the NativeReader.
    from unification.native_client import validate_generation
    manifest = json.loads((Path(partition)/'partition.json').read_text())
    registry = validate_generation(Path(registry_path),Path(partition),manifest)
    approved = {(r['evidence']['doc_id'],r['evidence']['revision']):r['evidence'] for r in manifest['records']}
    cases = pinned_cases()
    evaluator_paths = [Path(__file__), CASES_PATH, ROOT/'scripts/memory_unification_shadow_readers.py',
                       ROOT/'scripts/memory_unification_fact_review.py', ROOT/'scripts/memory_unification_eval.py']
    def evaluator_generation():
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evaluator_paths}
    evaluator_before = evaluator_generation()
    fingerprint = {'registry_sha256':hashlib.sha256(Path(registry_path).read_bytes()).hexdigest(),
        'public_manifest_sha256':digest(manifest),'case_set_sha256':hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        'corpus_sha256':digest(sorted(e[0] for e in approved)),
        'revisions_sha256':digest(sorted([list(e) for e in approved])),'coverage':registry.coverage}
    readers = {'legacy':legacy,'unified':unified}
    fingerprints = {name:backend_fingerprint(reader) for name,reader in readers.items()}
    report = {'version':2,'live_cutover':False,'fingerprints':fingerprint,'backend_fingerprints':fingerprints,
        'evaluator_generation':evaluator_before,'python_version':sys.version,
        'context':{'audience':'public','authority':'trusted local evaluation; not a session lease',
                   'legacy_campaign':'operator-baseline-only; NOT equivalent public-authority corpus'},
        'timing_note':'Experimental retrieval+required-read timings, no model/audio. Warm n=repeats-1 (two at repeats=3); p95 is that small sample maximum, NOT a full-wiki service estimate.',
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
                    if not isinstance(response,dict) or response.get('status') not in {'ok','empty','decline','stale','unavailable','denied'} or not isinstance(response.get('results'),list):
                        raise ValueError('normalized backend envelope required')
                    backends = response.get('backends')
                    if not isinstance(backends,list) or not backends or any(not isinstance(b,dict) for b in backends):
                        raise ValueError('explicit backend status required')
                    if response['status'] in {'ok','empty','decline'} and any(b.get('status') != 'ready' for b in backends):
                        raise ValueError('unavailable is not a healthy empty search')
                    if response.get('warning') or response.get('warnings') or response.get('disabled') or response.get('stale'):
                        response = {**response,'status':'unavailable','results':[], 'coverage':'partial'}
                    if response['status'] not in {'ok','empty','decline'} or any(b.get('status') != 'ready' for b in backends):
                        response = {**response,'coverage':'partial'}
                except Exception as error:
                    response = {'status':'unavailable','results':[],'coverage':'partial',
                        'backends':[{'id':name,'status':'unavailable','reason':type(error).__name__}]}
                elapsed = clock()-before
                runs[name].append({'run':repeat,'elapsed_s':elapsed,'status':response['status'],
                    'backend_status':[{'id':b.get('id'),'status':b.get('status')} for b in response.get('backends',[])],
                    'coverage':response.get('coverage','partial'),
                    'warning':response.get('warning'),
                    'passage_evidence': [{k:v for k,v in p.items() if k != 'text'} for p in response.get('passage_evidence',[])],
                    'ranked_references':ranked_evidence(response,approved,adapter=case['adapter'],fingerprint=fingerprints[name]),
                    'retrieval_correctness':retrieval_check(case,response),'answer_correctness':answer_check(response)})
        for name,observations in runs.items():
            healthy = [r['elapsed_s'] for r in observations if r['status'] in {'ok','empty','decline'}]
            warm = [r['elapsed_s'] for r in observations[1:] if r['status'] in {'ok','empty','decline'}]
            warm_stats = percentile_summary(warm)
            target = 4.5 if case['adapter']=='rules' else 2.0 if case['adapter'] in {'campaign','equipment'} else None
            measurable = (len(healthy)==repeats and len(warm)==repeats-1 and bool(warm)
                          and target is not None and fingerprints[name].get('status')=='available'
                          and fingerprints[name].get('measurement_scope') != 'synthetic-fixture')
            row['backends'][name] = {'runs':observations,'latency':percentile_summary(healthy),'warm_latency':warm_stats,
                'attempted_n':len(observations),'cold_first_s':observations[0]['elapsed_s'],
                'corpus_revision_fingerprint':fingerprints[name],
                'target':{'p95_s':target,'assessment':('met' if warm_stats['p95_s']<=target else 'unmet') if measurable else 'not_assessed'}}
        report['cases'].append(row)
    # Corpus edits during an evaluation invalidate its evidence, too.
    validate_generation(Path(registry_path),Path(partition),manifest)
    after = {name:backend_fingerprint(reader) for name,reader in readers.items()}
    if evaluator_generation() != evaluator_before or any(
            fingerprints[name].get('status') != 'available' or after[name] != fingerprints[name] for name in readers):
        from unification.policy import StaleReference
        raise StaleReference('measured backend generation unavailable or changed; reject paired evidence')
    report['backend_fingerprints_after'] = after
    report['generation_validation'] = 'unchanged-content-hashes'
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
    parser.add_argument('--fact-inventory',type=Path,help='optional revision-bound schema-v2 reviewed claim inventory')
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
