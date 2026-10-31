#!/usr/bin/env python3
"""Hermetic line-protocol peer. Never imports OpenClaw or opens a socket."""
import json
from pathlib import Path
import sys
import time

fixture = json.loads(Path(sys.argv[1]).read_text())
log = Path(fixture['log'])
with log.open('a') as output:
    output.write(json.dumps({'started': True})+'\n')
for line in sys.stdin:
    try:
        req = json.loads(line)
        with log.open('a') as output:
            output.write(json.dumps(req)+'\n')
        verb = req['verb']
        if verb == 'hello' and fixture.get('hello_hang'):
            time.sleep(10)
        if verb == 'hello' and fixture.get('startup_refusal'):
            raise SystemExit(3)
        if verb == 'search' and fixture.get('hang'):
            time.sleep(10)
        if verb == 'search' and fixture.get('delay_once'):
            time.sleep(fixture.pop('delay_once'))
        if verb == 'search' and fixture.get('die'):
            raise SystemExit(4)
        if verb == 'search' and fixture.get('mutate'):
            Path(fixture['mutate']).write_text('changed during I/O\n')
        if verb in {'search','get','health'}:
            reply = fixture.get('response', {'version':1,'status':'empty','results':[],
                'backends':[{'id':'openclaw','status':'ready'}],'coverage':'partial'})
        else:
            reply = {'status':'ok','coverage':'partial'}
        print(json.dumps({'id':req['id'],'ok':True,**reply,**({'query':req.get('query')} if verb=='search' else {})}),flush=True)
        if verb == 'shutdown':
            break
    except (KeyError, ValueError, TypeError):
        print(json.dumps({'ok':False,'error':'invalid request'}),flush=True)
