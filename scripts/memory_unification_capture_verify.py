#!/usr/bin/env python3
"""Private U3 import/replay/shared-read/restore verification; no live caller switch."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.dont_write_bytecode=True
from unification.capture import CaptureStore, _tokens
from unification.import_legacy import import_jsonl
from unification.policy import AccessContext, AccessDenied, Registry
from unification.service import MemoryService


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-root',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    os.umask(0o077)
    root=args.pilot_root
    source_before=args.source.read_bytes()
    store=CaptureStore(root/'store')
    started=time.monotonic()
    replay=import_jsonl(args.source,store,root/'imports',AccessContext('operator'))
    replay_s=time.monotonic()-started
    service=MemoryService(Registry([]),captures=store)
    rows=[]
    raw_rows=source_before.splitlines()
    canary=None
    for row in replay['rows']:
        if row['status']!='captured':
            continue
        value=json.loads(raw_rows[row['source_line']-1])
        fact=value.get('fact') or value.get('text')
        query=' '.join(_tokens(fact)[:12])
        record_id=row['receipt']['record_id']
        started=time.monotonic()
        response=service.search(query,AccessContext('operator'),domain='captured',limit=30)
        evidence=next((e for e in response['results'] if e['doc_id']=='capture/'+record_id),None)
        if evidence is None:
            raise RuntimeError('saved record missing from shared reader')
        got=service.get(evidence['doc_id'],AccessContext('operator'),revision=evidence['revision'],lines=200)
        expected='\n'.join(fact.splitlines())
        correct=(got['text']==expected and evidence['revision']==row['receipt']['revision'] and
                 evidence['origin']['revision']==row['row_revision'] and evidence['visibility']=='operator' and
                 evidence['claim_status']=='provisional' and evidence['promoted'] is False)
        if not correct:
            raise RuntimeError('saved source evidence/revision mismatch')
        rows.append({'record_id':record_id,'revision':evidence['revision'],'source_line':row['source_line'],
                     'exact_read':True,'passage_sha256':sha(got['text']),
                     'retrieval_and_get_s':time.monotonic()-started})
        if canary is None:
            canary=(query,evidence)
    public_denials=[]
    for operation in ('search','get'):
        try:
            if operation=='search':service.search(canary[0],AccessContext(),domain='captured')
            else:service.get(canary[1]['doc_id'],AccessContext())
        except AccessDenied:
            public_denials.append(operation)
    gm_empty=not service.search(canary[0],AccessContext('gm'),domain='captured')['results']
    command=[sys.executable,'-m','unification.capture_cli','--store',str(root/'store')]
    run=subprocess.run(command+['search','--q',canary[0],'--limit','30'],cwd=ROOT,
                       capture_output=True,text=True,check=True)
    cli=json.loads(run.stdout)
    same_cli_evidence=any(e['doc_id']==canary[1]['doc_id'] and e['revision']==canary[1]['revision']
                          for e in cli['results'])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    scratch=root/('restore-rehearsal-'+stamp)
    shutil.copytree(root/'store',scratch)
    # Only a generated scratch index is removed; canonical originals and the
    # imported store remain untouched. Source inventory must survive independently.
    (scratch/'index.sqlite').unlink()
    rebuilt=CaptureStore(scratch).recover()
    recovered=store.recover()
    max_lag=max(recovered['saved_to_searchable_ms'],default=None)
    unchanged=args.source.read_bytes()==source_before
    report={'version':1,'model':'openai/gpt-6.1-sol','thinking':'high','live_cutover':False,
            'source_sha256':sha(source_before),'source_unchanged':unchanged,
            'replay_receipt':replay['receipt_path'],'replay_new_records':replay['new_records'],
            'saved':replay['saved_records'],'searchable':replay['searchable_records'],
            'promoted':replay['promoted_records'],'exact_shared_reads':len(rows),'read_receipts':rows,
            'replay_elapsed_s':replay_s,'saved_to_searchable_max_ms':max_lag,
            'freshness_under_5s':max_lag is not None and max_lag<=5000,
            'public_search_get_denied':public_denials==['search','get'],'gm_cannot_read_operator_rows':gm_empty,
            'operator_cli_same_revision':same_cli_evidence,'scratch_index_rebuilt':rebuilt['saved_records']==replay['saved_records'],
            'code_sha256':{p:sha((ROOT/p).read_bytes()) for p in ('unification/capture.py',
                'unification/import_legacy.py','unification/service.py','unification/capture_cli.py',
                'scripts/memory_unification_capture_verify.py')},
            'note':'Isolated private/provisional store and explicit operator CLI only. No public canon promotion or production capture/search routing.'}
    checks=(unchanged and replay['new_records']==0 and len(rows)==replay['captured_rows'] and
            report['freshness_under_5s'] and report['public_search_get_denied'] and gm_empty and same_cli_evidence and
            report['scratch_index_rebuilt'] and replay['promoted_records']==0)
    report['passed']=checks
    path=root/(stamp+'-verification.private.json')
    with path.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({'receipt':str(path),**{k:report[k] for k in ('passed','saved','searchable','promoted',
        'exact_shared_reads','replay_new_records','saved_to_searchable_max_ms','operator_cli_same_revision',
        'public_search_get_denied','scratch_index_rebuilt','source_unchanged')}}))
    if not checks:raise SystemExit(1)


if __name__=='__main__':
    main()
