#!/usr/bin/env python3
"""Private, repeatable recovery baseline. Never prints source/config contents.

Copies mutable source/code, uses SQLite's online backup, inventories raw PDFs.
Does not inspect session content, change config, refresh indexes or restart services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

CODE = Path('/Users/hanclaw/claw/projects/cindylou')
DATA = Path('/Volumes/carbonite/claw/data/cindylou')
CLAW = Path.home() / '.openclaw'
WORKSPACE = CLAW / 'workspace-cindylou'
DEFAULT_ROOT = DATA / 'runtime/memory-unification'
SKIP = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'dist',
        'logs', 'runtime', 'rollback', 'backups', '.AppleDouble'}


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def selected(root: Path, kind: str):
    if root.is_file():
        yield root
        return
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('rollback-')
                         and (not d.startswith('.') or d == '.dreams'))
        for name in sorted(files):
            p = Path(base) / name
            if name.startswith('._') or p.is_symlink():
                continue
            rel = p.relative_to(root)
            if kind == 'workspace':
                eligible = ((rel.parts[0] == 'memory' and p.suffix in {'.md','.json','.jsonl','.txt','.migrated'})
                            or (len(rel.parts) == 1 and p.suffix == '.md'))
            elif kind == 'documents':
                eligible = p.suffix in {'.md', '.jsonl', '.json', '.yaml', '.yml'}
            elif kind == 'dreams':
                eligible = True  # copy-only recovery of hidden dream journals/retained evidence
            elif kind == 'services':
                eligible = p.suffix == '.plist' and any(word in p.name.lower() for word in ['cindylou','memory'])
            else:
                eligible = p.suffix in {'.py', '.sh', '.md', '.js', '.ts', '.json', '.toml'} or name in {'.env', '.env.example', '.gitignore'}
            if eligible:
                yield p


def backup_db(source: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst, pages=512, sleep=0.05)
            check = dst.execute('PRAGMA quick_check').fetchall()
            if check != [('ok',)]:
                raise RuntimeError('SQLite integrity check failed: ' + source.name)
    target.chmod(0o600)
    return {'source': str(source), 'snapshot': str(target), 'sha256': digest(target),
            'bytes': target.stat().st_size, 'quick_check': 'ok',
            'restore_policy': 'forensic snapshot; never overwrite live mixed-agent DB'}


def capture(out: Path) -> dict:
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    entries, errors, missing = [], [], []
    roots = [
        ('workspace', WORKSPACE, 'workspace'),
        ('cleaned-memory', DATA / 'cleaned/memory', 'documents'),
        ('campaign-wiki', CODE / 'campaign-wiki', 'documents'),
        ('production-memory-code', CODE / 'memory-system', 'code'),
        ('production-bridge-code', CODE.parent / 'discord_voice_patch', 'code'),
        ('launchagents', Path.home() / 'Library/LaunchAgents', 'services'),
    ]
    for label, root, kind in roots:
        if not root.exists():
            missing.append(str(root)); continue
        for src in selected(root, kind):
            dest = out / 'sources' / label / src.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                before = (src.stat().st_size, src.stat().st_mtime_ns)
                shutil.copyfile(src, dest)
                dest.chmod(0o600)
                content_hash = digest(dest)
                # Detect live edits instead of claiming a coherent source snapshot.
                if before != (src.stat().st_size, src.stat().st_mtime_ns) or content_hash != digest(src):
                    raise RuntimeError('source changed during snapshot')
                entries.append({'source': str(src), 'snapshot': str(dest.relative_to(out)),
                                'sha256': content_hash, 'bytes': dest.stat().st_size,
                                'mtime_ns': before[1]})
            except Exception as e:
                errors.append({'source': str(src), 'error': str(e)})
    config = CLAW / 'openclaw.json'
    if config.exists():
        dest = out / 'openclaw.config.private.json'
        shutil.copyfile(config, dest); dest.chmod(0o600)
        cfg = json.loads(dest.read_text())
        # Only safe memory keys appear in the machine-readable summary.
        mem = cfg.get('memory', {})
        (out / 'memory-config.json').write_text(json.dumps({'memory': mem}, indent=2) + '\n')
        entries.append({'source': str(config), 'snapshot': dest.name, 'sha256': digest(dest), 'bytes': dest.stat().st_size})
    else:
        missing.append(str(config))
    dbs = []
    for label, src in [
        ('agent', CLAW / 'agents/cindylou/agent/openclaw-agent.sqlite'),
        ('equipment', DATA / 'cache/sr3data/sr3data.sqlite'),
        ('control-state', CLAW / 'state/openclaw.sqlite'),
    ]:
        if src.exists():
            try:
                dbs.append(backup_db(src, out / 'databases' / (label + '.sqlite')))
            except Exception as e:
                errors.append({'source': str(src), 'error': str(e)})
        else:
            missing.append(str(src))
    repos = {}
    for name, root in [('memory', CODE/'memory-system'), ('wiki', CODE/'campaign-wiki'),
                       ('bridge', CODE.parent/'discord_voice_patch'), ('openclaw', CODE.parents[1]/'openclaw')]:
        def git(*args):
            r = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=20)
            if r.returncode:
                raise RuntimeError('git command failed: ' + name)
            return r.stdout
        try:
            repos[name] = {'root': str(root), 'head': git('rev-parse', 'HEAD').strip(),
                           'status': git('status', '--short'), 'diff_sha256': hashlib.sha256(git('diff', '--binary', 'HEAD').encode()).hexdigest()}
            (out / (name + '.preexisting.patch')).write_text(git('diff', '--binary', 'HEAD'))
        except Exception as e:
            errors.append({'repo': name, 'error': str(e)})
    pdf_root = Path('/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e')
    pdfs = [{'path': str(p), 'bytes': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns}
            for p in pdf_root.rglob('*.pdf') if not p.name.startswith('._')] if pdf_root.exists() else []
    manifest = {'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'snapshot': str(out), 'files': entries, 'databases': dbs, 'repos': repos,
                'raw_pdfs_inventory_only': pdfs, 'errors': errors, 'missing': missing,
                'consistent_global_instant': False,
                'note': 'per-file consistent and SQLite online consistent, not a globally frozen box'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verify(out: Path) -> dict:
    m = json.loads((out/'manifest.json').read_text())
    failures = []
    for entry in m['files']:
        p = out / entry['snapshot']
        if not p.is_file() or digest(p) != entry['sha256']:
            failures.append(entry['snapshot'])
    for entry in m['databases']:
        p = Path(entry['snapshot'])
        if digest(p) != entry['sha256']:
            failures.append(p.name)
        with sqlite3.connect(p.as_uri()+'?mode=ro', uri=True) as db:
            if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                failures.append(p.name + ':integrity')
    # Rehearse restoration WITHOUT touching live source or runtime databases.
    rehearsal = out/'restore-rehearsal'
    rehearsal.mkdir(mode=0o700, exist_ok=True)
    if m['files']:
        sample = next((e for e in m['files'] if e['source'].endswith('chat_facts.jsonl')), m['files'][0])
        dest = rehearsal/'source-copy'
        shutil.copyfile(out/sample['snapshot'], dest)
        if digest(dest) != sample['sha256']:
            failures.append('source-restore')
    if m['databases']:
        entry = next((e for e in m['databases'] if 'equipment' in e['snapshot']), m['databases'][0])
        copied = backup_db(Path(entry['snapshot']), rehearsal/'restored.sqlite')
        # SQLite backup may normalize physical pages: verify logical integrity, not bytes.
        if copied['quick_check'] != 'ok':
            failures.append('database-restore')
    result = {'files_verified': len(m['files']), 'databases_verified': len(m['databases']),
              'failures': failures, 'capture_errors': m['errors'], 'missing': m['missing'],
              'restore_rehearsal': str(rehearsal), 'ok': not failures and not m['errors'] and not m['missing']}
    (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    ap.add_argument('--verify', type=Path)
    ap.add_argument('--supplement', type=Path,
                    help='repair initial OpenClaw repo path and add omitted hidden dream source files')
    args = ap.parse_args()
    os.umask(0o077)
    if args.supplement:
        out = args.supplement
        manifest_path = out/'manifest.json'
        m = json.loads(manifest_path.read_text())
        already = {e['source'] for e in m['files']}
        added = 0
        control_db = CLAW/'state/openclaw.sqlite'
        if control_db.exists() and not any(d['source']==str(control_db) for d in m['databases']):
            m['databases'].append(backup_db(control_db,out/'databases/control-state.sqlite'))
        # Service definitions are recovery inputs; copying does not load or restart them.
        for src in (Path.home()/'Library/LaunchAgents').glob('*.plist'):
            if not any(word in src.name.lower() for word in ['cindylou','memory']):
                continue
            if str(src) in already:
                continue
            dest=out/'sources/launchagents'/src.name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dest);dest.chmod(0o600)
            sha=digest(dest)
            if sha != digest(src):
                raise RuntimeError('service definition changed during snapshot')
            m['files'].append({'source':str(src),'snapshot':str(dest.relative_to(out)),
                               'sha256':sha,'bytes':dest.stat().st_size,'mtime_ns':src.stat().st_mtime_ns})
            added += 1
        for src in selected(WORKSPACE/'memory/.dreams', 'dreams'):
            if str(src) in already:
                continue
            dest = out/'sources/workspace'/src.relative_to(WORKSPACE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src,dest); dest.chmod(0o600)
            sha = digest(dest)
            if sha != digest(src):
                raise RuntimeError('source changed during supplement')
            m['files'].append({'source':str(src),'snapshot':str(dest.relative_to(out)),
                               'sha256':sha,'bytes':dest.stat().st_size,'mtime_ns':src.stat().st_mtime_ns})
            added += 1
        root = CODE.parents[1]/'openclaw'
        def git(*args):
            return subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,
                                  check=True,timeout=20).stdout
        diff = git('diff','--binary','HEAD')
        m['repos']['openclaw'] = {'root':str(root),'head':git('rev-parse','HEAD').strip(),
                                 'status':git('status','--short'),
                                 'diff_sha256':hashlib.sha256(diff.encode()).hexdigest()}
        (out/'openclaw.preexisting.patch').write_text(diff)
        corrected = [e for e in m['errors'] if e.get('repo') == 'openclaw']
        m['errors'] = [e for e in m['errors'] if e.get('repo') != 'openclaw']
        m.setdefault('supplements',[]).append({'at':datetime.now(timezone.utc).isoformat(),
            'added_files':added,'resolved_errors':corrected,'reason':'initial collector path/hidden-directory fixes'})
        manifest_path.write_text(json.dumps(m,indent=2)+'\n')
        result = verify(out)
    elif args.verify:
        result = verify(args.verify)
    else:
        out = args.root/'baselines'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        start = time.monotonic()
        m = capture(out)
        result = verify(out)
        result.update(snapshot=str(out), elapsed_s=round(time.monotonic()-start, 3),
                      bytes_copied=sum(e['bytes'] for e in m['files'])+sum(e['bytes'] for e in m['databases']))
    # Only safe counts and locations; no facts, diffs, session rows, config values.
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
