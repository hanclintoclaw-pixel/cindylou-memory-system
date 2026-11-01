#!/usr/bin/env python3
"""Atomically checkpoint this migration, outside git and production memory."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import uuid

CONTROL = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--batch',choices=['U0','U1','U2','U3','U4','U5'])
    ap.add_argument('--status',choices=['pending','in_progress','completed','blocked'])
    ap.add_argument('--next-action')
    ap.add_argument('--note')
    ap.add_argument('--commit')
    ap.add_argument('--artifact',action='append',default=[],help='name=absolute-path')
    ap.add_argument('--verified',action='append',default=[],help='resolved entry removed from unverified')
    ap.add_argument('--completed',action='append',default=[],help='completed bounded deliverable')
    ap.add_argument('--check',action='append',default=[],help='name=observed verification result')
    ap.add_argument('--live-change',action='append',default=[],help='bounded installed change; not a broader deployment claim')
    args=ap.parse_args()
    os.umask(0o077)
    with (CONTROL/'checkpoint.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads((CONTROL/'STATE.json').read_text())
        if not args.batch:
            print(json.dumps(state,indent=2)); return
        if not args.status or not args.next_action or not args.note:
            ap.error('a checkpoint requires batch, status, next-action and note')
        event_id=str(uuid.uuid4())
        now=datetime.now(timezone.utc).isoformat()
        state.update(updated_at=now,current_batch=args.batch,next_action=args.next_action,
                     checkpoint_id=event_id,active_processes=[])
        state.setdefault('batches',{})[args.batch]={'status':args.status,'last_checkpoint':event_id}
        if args.commit:
            # Store an immutable revision, never a moving symbolic HEAD/ref.
            state['commit']=subprocess.run(['git','-C',state['worktree'],'rev-parse',
                '--verify','--end-of-options',args.commit+'^{commit}'],check=True,
                capture_output=True,text=True).stdout.strip()
        for item in args.verified:
            state['unverified']=[old for old in state.get('unverified',[]) if old != item]
            if item not in state.setdefault('verified',[]):state['verified'].append(item)
        for item in args.completed:
            if item not in state.setdefault('completed',[]):state['completed'].append(item)
        for item in args.live_change:
            if item not in state.setdefault('live_changes',[]):state['live_changes'].append(item)
        for item in args.check:
            name,separator,value=item.partition('=')
            if not separator or not name or not value:ap.error('checks require name=result')
            state.setdefault('last_checks',{})[name]=value
        for item in args.artifact:
            name,separator,value=item.partition('=')
            if not separator or not name or not Path(value).is_absolute() or not Path(value).exists():
                ap.error('artifacts require name=existing-absolute-path')
            state.setdefault('artifacts',{})[name]=value
        with (CONTROL/'JOURNAL.md').open('a') as journal:
            journal.write(f'\n## {now} — {args.batch} {args.status} ({event_id})\n\n{args.note}\n\nNext: {args.next_action}\n')
            journal.flush(); os.fsync(journal.fileno())
        temporary=CONTROL/('STATE.'+event_id+'.tmp')
        with temporary.open('x') as f:
            json.dump(state,f,indent=2); f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(temporary,CONTROL/'STATE.json')
        print(json.dumps({'checkpoint':event_id,'batch':args.batch,'status':args.status},indent=2))


if __name__ == '__main__':
    main()
