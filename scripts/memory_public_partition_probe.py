#!/usr/bin/env python3
"""Run the installed native spike with source/view checks before AND after I/O."""
import argparse
from datetime import datetime, timezone
import shutil
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unification.partition import validate_public
from unification.registry import load_registry


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registry',type=Path,required=True)
    ap.add_argument('--partition',type=Path,required=True)
    ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--revision',required=True)
    args=ap.parse_args()
    manifest=json.loads((args.partition/'partition.json').read_text())
    validate_public(load_registry(args.registry),args.partition,manifest)
    env={k:v for k,v in os.environ.items() if not k.startswith('OPENCLAW_')}
    env.update(OPENCLAW_STATE_DIR=str(args.partition/'state'),OPENCLAW_CONFIG_PATH=str(args.partition/'openclaw.json'))
    # Keep failed experiments as evidence; never replace the only failure record.
    history=args.partition/'attempts'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    history.mkdir(parents=True,mode=0o700)
    for filename in ['native-report.json','boundary-report.json','native-process.log']:
        old=args.partition/filename
        if old.exists(): shutil.copy2(old,history/filename)
    run=subprocess.run(['node',str(Path(__file__).with_name('memory_public_native_spike.mjs')),
                        str(args.runtime),str(args.partition),args.revision],env=env,
                       capture_output=True,text=True,timeout=180)
    (args.partition/'native-process.log').write_text(run.stdout+run.stderr)
    # Reload the authority manifest: an approval revoked during I/O is not valid.
    validate_public(load_registry(args.registry),args.partition,manifest)
    result={'before_after_eligibility':'passed','native_exit_code':run.returncode,
            'native_report':str(args.partition/'native-report.json')}
    (args.partition/'boundary-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return run.returncode


if __name__=='__main__':
    raise SystemExit(main())
