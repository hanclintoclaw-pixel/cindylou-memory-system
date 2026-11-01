#!/usr/bin/env python3
"""Install a separate pinned public CLI; never replace an existing command.

Exports committed unification code only. Registry/partition remain authoritative
local configuration, not copies or new disclosure grants. No services are touched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def install(repo, revision, registry, partition, releases, bin_dir):
    repo, registry, partition = map(lambda p: Path(p).resolve(strict=True), (repo, registry, partition))
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    commit = git('rev-parse', '--verify', '--end-of-options', revision+'^{commit}').decode().strip()
    if not registry.is_file() or not (partition/'partition.json').is_file():
        raise ValueError('reviewed registry and partition required')
    releases, bin_dir = Path(releases).absolute(), Path(bin_dir).absolute()
    target = bin_dir/'cindylou-canary'
    if os.path.lexists(target):
        raise FileExistsError('refusing to replace existing canary command')
    releases.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    release = releases/commit
    if os.path.lexists(release):
        raise FileExistsError('refusing to replace existing release')
    # Export blobs rather than copying mutable worktree files or private runtime data.
    entries = git('ls-tree', '-r', '-z', commit, '--', 'unification').split(b'\0')
    files = {}
    for entry in filter(None, entries):
        meta, raw_path = entry.split(b'\t', 1)
        mode, kind, object_id = meta.split()
        name = raw_path.decode()
        if kind != b'blob' or mode != b'100644' or not name.startswith('unification/'):
            raise ValueError('unexpected release entry')
        files[name] = git('cat-file', 'blob', object_id.decode())
    if 'unification/canary_cli.py' not in files:
        raise ValueError('revision lacks canary')
    manifest = {'version': 1, 'commit': commit, 'python': sys.executable,
                'registry': str(registry), 'partition': str(partition),
                'files': {name: sha(data) for name, data in files.items()}}
    launcher = '''import hashlib, json, sys
from pathlib import Path
root = Path(__file__).resolve().parent
# Disabled calls exit before reading registry, partition or importing release code.
if '--enable-canary' not in sys.argv[1:]:
    print('canary disabled; explicit --enable-canary required', file=sys.stderr)
    raise SystemExit(2)
try:
    manifest = json.loads((root/'release.json').read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise ValueError('release integrity failure')
except Exception:
    print(json.dumps({'version':1,'status':'unavailable','reason':'installed release integrity failure','results':[]}))
    raise SystemExit(5)
sys.path.insert(0, str(root))
from unification.canary_cli import parser, execute
ap = parser()
ap.allow_abbrev = False
args = ap.parse_args(['--registry', manifest['registry'], '--partition', manifest['partition']] + sys.argv[1:])
if str(args.registry) != manifest['registry'] or str(args.partition) != manifest['partition']:
    ap.error('installed canary inputs are fixed; no registry/partition override')
try:
    result = execute(args)
except ValueError as error:
    ap.error(str(error))
result['caller'].update(installed_entrypoint=True, release_commit=manifest['commit'])
print(json.dumps(result, indent=2, allow_nan=False))
raise SystemExit({'denied':3,'stale':4,'unavailable':5}.get(result.get('status'),0))
'''
    wrapper = '#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -I '+shlex.quote(str(release/'launch.py'))+' "$@"\n'
    # Build off-path; publish complete release before exclusive command creation.
    with tempfile.TemporaryDirectory(prefix='.canary-', dir=releases) as temporary:
        staging = Path(temporary)/'release'
        staging.mkdir()
        for name, data in files.items():
            path = staging/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (staging/'release.json').write_text(json.dumps(manifest, indent=2)+'\n')
        (staging/'launch.py').write_text(launcher)
        (staging/'command.sh').write_text(wrapper)
        (staging/'command.sh').chmod(0o700)
        os.rename(staging, release)
    # Atomic no-overwrite publication, including dangling/concurrent symlinks.
    target.symlink_to(release/'command.sh')
    return {'version':1,'installed_at':datetime.now(timezone.utc).isoformat(),
            'commit':commit,'command':str(target),'release':str(release),
            'registry':str(registry),'partition':str(partition),
            'files':manifest['files'],'wrapper_sha256':sha(wrapper.encode()),
            'launcher_sha256':sha(launcher.encode()),
            'scope':'separate default-off public campaign CLI; primary CLI/API/voice unchanged',
            'rollback':'stop invoking cindylou-canary or omit --enable-canary; preserve release and records'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision', required=True)
    ap.add_argument('--registry', type=Path, required=True)
    ap.add_argument('--partition', type=Path, required=True)
    ap.add_argument('--releases', type=Path, required=True)
    ap.add_argument('--bin-dir', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    if args.receipt.exists():
        ap.error('receipt already exists')
    receipt = install(ROOT,args.revision,args.registry,args.partition,args.releases,args.bin_dir)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x') as out:
        json.dump(receipt,out,indent=2)
        out.write('\n')
    print(json.dumps({'installed':receipt['command'],'commit':receipt['commit'],'receipt':str(args.receipt)}))
