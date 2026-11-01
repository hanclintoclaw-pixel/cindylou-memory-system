#!/usr/bin/env python3
"""Exercise the actual foreground API briefly on a private ephemeral loopback port.

No persistent service, existing listener change, token disclosure or source rebuild.
Receipts contain response hashes/statuses/timings, never tokens or source passages.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from unification.policy import AccessContext
from unification.registry import load_registry


def verify(registry,partition,output_root):
    os.umask(0o077)
    output=output_root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'version':1,'scope':'ephemeral actual foreground API; not persistent deployment',
            'coverage':'partial','checks':[],'passed':False,
            'native_runtime_state':'isolated partition index/recall state may update',
            'latency_scope':'serialized HTTP request including per-request native startup/shutdown; not warm p95'}
    receipt=output/'api-verification.private.json'
    process=None
    def check(label,passed,**fields):
        report['checks'].append({'label':label,'passed':bool(passed),**fields})
        if not passed:
            raise RuntimeError('API verification check failed')
    try:
        docs=list(load_registry(registry).documents(AccessContext(),'campaign'))
        inputs=[registry,partition/'partition.json',partition/'openclaw.json',Path(__file__)]
        inputs += list((ROOT/'unification').glob('*.py'))+list((ROOT/'unification').glob('*.mjs'))
        inputs += [doc.source.root/doc.doc_id.split('#')[0].split('/',1)[1] for doc in docs]
        def hashes():
            return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(set(inputs))}
        report['inputs_before']=hashes()
        with tempfile.TemporaryDirectory(dir=output,prefix='ephemeral-') as scratch:
            token=secrets.token_urlsafe(32)
            token_file=Path(scratch)/'route-token'
            token_file.write_text(token+'\n')
            token_file.chmod(0o600)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0))
                port=probe.getsockname()[1]
            base=[sys.executable,'-m','unification.canary_api','--registry',str(registry),
                  '--partition',str(partition),'--token-file',str(token_file),'--port',str(port)]
            disabled=subprocess.run(base,cwd=ROOT,capture_output=True,timeout=5)
            check('default-off before startup',disabled.returncode==2)
            process=subprocess.Popen(base+['--enable-canary'],cwd=ROOT,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,start_new_session=True)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                ready=bool(selector.select(15))
                line=process.stdout.readline() if ready else b''
            check('actual foreground loopback startup',b'listening on loopback' in line and process.poll() is None,
                  startup_line_sha256=hashlib.sha256(line).hexdigest(),exit_code=process.poll())
            def request(label,method,path,expected,body=None,*,auth=True,origin=False,predicate=lambda p:True):
                headers={'Content-Type':'application/json'}
                if auth:headers['Authorization']='Bearer '+token
                if origin:headers['Origin']='http://localhost'
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=65)
                start=time.monotonic()
                try:
                    connection.request(method,path,body=None if body is None else json.dumps(body),headers=headers)
                    response=connection.getresponse()
                    raw=response.read()
                    payload=json.loads(raw)
                    check(label,response.status==expected and predicate(payload),http_status=response.status,
                        status=payload.get('status'),elapsed_s=time.monotonic()-start,
                        response_sha256=hashlib.sha256(raw).hexdigest())
                    return payload
                finally:
                    connection.close()
            request('unauthenticated health denied','GET','/v1/health',401,auth=False)
            request('browser origin denied','GET','/v1/health',403,origin=True)
            request('authenticated native health','GET','/v1/health',200,predicate=lambda p:p.get('status')=='ok')
            for doc in docs:
                query=Path(doc.doc_id.split('#')[0]).stem.replace('-',' ')
                request('search '+doc.doc_id,'POST','/v1/search',200,{'query':query},
                    predicate=lambda p:any(h.get('doc_id')==doc.doc_id and h.get('revision')==doc.revision for h in p.get('results',[])))
                offset=2 if len(doc.content.splitlines())>1 else 1
                expected=doc.content.splitlines()[offset-1]
                request('exact bounded read '+doc.doc_id,'POST','/v1/get',200,
                    {'doc_id':doc.doc_id,'revision':doc.revision,'start_line':offset,'lines':1},
                    predicate=lambda p:p.get('text')==expected and p.get('source_line')==doc.section.start_line+offset-1)
            doc=docs[0]
            request('stale revision','POST','/v1/get',409,{'doc_id':doc.doc_id,'revision':'0'*64},predicate=lambda p:not p.get('text'))
            request('unknown source denied','POST','/v1/get',403,{'doc_id':'wiki/Unapproved.md#missing','revision':'0'*64},predicate=lambda p:not p.get('text'))
            request('oversized read refused','POST','/v1/get',400,{'doc_id':doc.doc_id,'revision':doc.revision,'lines':201})
            request('audience override refused','POST','/v1/search',400,{'query':'Tom','audience':'operator'})
            request('write route absent','POST','/facts',404,{'text':'never written'})
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
            check('foreground stop and child teardown',process.returncode==0)
            with socket.socket() as probe:
                probe.settimeout(2)
                check('rollback listener closed',probe.connect_ex(('127.0.0.1',port))!=0)
            disabled=subprocess.run(base,cwd=ROOT,capture_output=True,timeout=5)
            check('rollback remains default-off',disabled.returncode==2)
        report['inputs_after']=hashes()
        check('authority and code hashes unchanged',report['inputs_before']==report['inputs_after'])
        report['passed']=True
    except Exception as error:
        report['failure_type']=type(error).__name__
    finally:
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()
        receipt.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'receipt':str(receipt),'passed':report['passed'],'checks':len(report['checks'])}))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registry',type=Path,required=True)
    ap.add_argument('--partition',type=Path,required=True)
    ap.add_argument('--output-root',type=Path,required=True)
    args=ap.parse_args()
    raise SystemExit(verify(args.registry,args.partition,args.output_root))
