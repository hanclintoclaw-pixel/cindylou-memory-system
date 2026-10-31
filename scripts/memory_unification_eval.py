#!/usr/bin/env python3
"""Run fixed legacy retrieval probes; save evidence PRIVATELY, print counts only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = Path('/Users/hanclaw/claw/projects/cindylou/memory-system')
CONTROL = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')


def run_case(case: dict) -> dict:
    adapter, query = case['adapter'], case['query']
    if adapter == 'campaign':
        cmd = [sys.executable,str(PRODUCTION/'cindylou.py'),'search','--scope','campaign','--q',query,'--limit','5']
    elif adapter == 'rules':
        cmd = [sys.executable,str(PRODUCTION/'cindylou.py'),'rules-answer','--q',query,'--limit','3']
    elif adapter == 'equipment':
        raise RuntimeError('equipment CLI can save production cache; use the controlled paired shadow readers')
    elif adapter == 'native-operator':
        raise RuntimeError('live native CLI can write recall/index state; excluded from controlled verification')
    else:
        raise ValueError('unknown baseline adapter')
    start = time.monotonic()
    run = subprocess.run(cmd,capture_output=True,text=True,timeout=35,
                         env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    elapsed = time.monotonic()-start
    try:
        result = json.loads(run.stdout)
    except json.JSONDecodeError:
        result = {'invalid_json':True}
    checks = {'process_success':run.returncode == 0, 'valid_json':'invalid_json' not in result}
    hits = result.get('results',[]) if isinstance(result,dict) else result
    if case.get('expected_doc'):
        checks['expected_doc_in_top5'] = any(h.get('doc_id') == case['expected_doc'] for h in hits)
    if case.get('expected_empty'):
        checks['empty'] = not hits
    if case.get('expected_decline'):
        checks['declined'] = result.get('accepted') is False
    if case.get('expected_name'):
        returned = [h for h in result.get('returned',[]) if h.get('name','').casefold() == case['expected_name'].casefold()]
        checks['named_citable_candidate'] = any(h.get('tier') in {'VERIFIED','SR3'} for h in returned)
        checks['citation_preserved'] = any(h.get('cite','').split(' -> ',1)[0] == case['expected_citation'] for h in returned)
        checks['damage_exact'] = any(h.get('fields',{}).get('Damage') == case['expected_damage'] for h in returned)
    source_check = None
    if case.get('required_source_terms'):
        # Read the canonical page directly to distinguish retrieval from corpus absence.
        source = Path('/Users/hanclaw/claw/projects/cindylou/campaign-wiki')/case['expected_doc'].removeprefix('wiki/')
        text = source.read_text()
        source_check = {'path':str(source),'revision':hashlib.sha256(text.encode()).hexdigest(),
                        'terms_present':all(t in text for t in case['required_source_terms'])}
        checks['source_fact_present'] = source_check['terms_present']
    return {'elapsed_s':round(elapsed,4),'returncode':run.returncode,'checks':checks,
            'result':result,'stderr':run.stderr[-2000:],'source_check':source_check}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repeats',type=int,default=3)
    ap.add_argument('--out',type=Path)
    ap.add_argument('--case',action='append',default=[],help='run only named case(s)')
    args = ap.parse_args()
    if not 1 <= args.repeats <= 10:
        ap.error('repeats must be 1..10')
    os.umask(0o077)
    cases = json.loads((ROOT/'docs/memory-unification/eval-cases.json').read_text())['cases']
    if args.case:
        selected_cases = [c for c in cases if c['id'] in args.case]
        if len(selected_cases) != len(set(args.case)):
            ap.error('unknown case ID')
        cases = selected_cases
    out = args.out or CONTROL/'evaluations'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,mode=0o700,exist_ok=False)
    evidence, summary = [], []
    # Sequential: CPU/embedding contention would invalidate the live-latency baseline.
    for case in cases:
        rows = []
        for _ in range(args.repeats):
            try:
                rows.append(run_case(case))
            except Exception as e:
                rows.append({'checks':{'completed':False},'error':type(e).__name__})
        durations = sorted(r['elapsed_s'] for r in rows if 'elapsed_s' in r)
        passed = sum(all(r['checks'].values()) for r in rows)
        evidence.append({'case':case,'runs':rows})
        summary.append({'case':case['id'],'runs':len(rows),'checks_passed_runs':passed,
                        'p50_s':round(statistics.median(durations),4) if durations else None,
                        'p95_s':durations[math.ceil(.95*len(durations))-1] if durations else None,
                        'cold_first_s':rows[0].get('elapsed_s'),
                        'observe_only':case.get('observe_only',False)})
        # Persist after EACH case so a reset does not lose completed measurements.
        (out/'evidence.private.json').write_text(json.dumps(evidence,indent=2)+'\n')
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'output':str(out),'cases':len(summary),'runs':sum(s['runs'] for s in summary),
        'all_checks_passed_cases':sum(s['checks_passed_runs']==s['runs'] for s in summary),
        'note':'Observed legacy results; failures are baseline findings, not test-suite failure.'},indent=2))


if __name__ == '__main__':
    main()
