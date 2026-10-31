#!/usr/bin/env python3
"""Verify the isolated public CLI caller; never install, approve or rebuild inputs.

Private receipts contain IDs/hashes/timings, not retrieved source text. Native
search may update the supplied isolated partition's runtime index/recall state.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from unification.policy import AccessContext
from unification.registry import load_registry


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(registry, partition, output_root):
    os.umask(0o077)
    output = output_root / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {'version': 1, 'scope': 'isolated-public-campaign-cli', 'production_installed': False,
              'registry': str(registry), 'partition': str(partition), 'checks': [], 'passed': False,
              'latency_scope': 'fresh CLI process including startup/search/shutdown; not warm retrieval',
              'native_runtime_state': 'supplied isolated partition may update indexes/recall state'}
    path = output / 'canary-verification.private.json'
    base = [sys.executable, '-m', 'unification.canary_cli', '--registry', str(registry),
            '--partition', str(partition)]
    def invoke(label, command, code, *, enabled=True, predicate=lambda payload: True):
        start = time.monotonic()
        run = subprocess.run(base + (['--enable-canary'] if enabled else []) + command,
                             cwd=ROOT, capture_output=True, text=True, timeout=45)
        elapsed = time.monotonic() - start
        payload = json.loads(run.stdout) if run.stdout else {}
        passed = run.returncode == code and predicate(payload)
        report['checks'].append({'label': label, 'exit_code': run.returncode,
            'status': payload.get('status'), 'elapsed_s': elapsed, 'passed': passed,
            'stdout_sha256': hashlib.sha256(run.stdout.encode()).hexdigest(),
            'stderr_sha256': hashlib.sha256(run.stderr.encode()).hexdigest()})
        if not passed:
            raise RuntimeError('caller check failed: ' + label)
        return payload, elapsed
    try:
        docs = list(load_registry(registry).documents(AccessContext(), 'campaign'))
        if not docs:
            raise ValueError('reviewed campaign inputs required')
        inputs = [registry, partition/'partition.json', partition/'openclaw.json']
        inputs += [doc.source.root / doc.doc_id.split('#')[0].split('/', 1)[1] for doc in docs]
        inputs += list((ROOT/'unification').glob('*.py')) + list((ROOT/'unification').glob('*.mjs')) + [Path(__file__)]
        before = {str(p): sha(p) for p in sorted(set(inputs))}
        report['input_revisions_before'] = before
        report['coverage'] = 'partial'
        invoke('default-off rollback', ['health'], 2, enabled=False)
        invoke('native health', ['health'], 0, predicate=lambda p: p.get('status') == 'ok')
        for doc in docs:
            samples = []
            query = Path(doc.doc_id.split('#')[0]).stem.replace('-', ' ')
            for sample in range(3):
                found, elapsed = invoke(f'search {doc.doc_id} sample {sample+1}', ['search', '--q', query], 0,
                    predicate=lambda p: p.get('status') == 'ok' and p.get('coverage') == 'partial'
                        and any(h.get('doc_id') == doc.doc_id and h.get('revision') == doc.revision for h in p.get('results', [])))
                samples.append(elapsed)
            report.setdefault('latency', []).append({'doc_id': doc.doc_id, 'n': len(samples),
                'p50_s': statistics.median(samples), 'p95_s': max(samples),
                'p95_note': 'three fresh processes; sample maximum, not a service estimate'})
            offset = 2 if len(doc.content.splitlines()) > 1 else 1
            expected = '\n'.join(doc.content.splitlines()[offset-1:offset])
            got, _ = invoke('bounded exact read '+doc.doc_id, ['get', doc.doc_id, '--revision', doc.revision,
                '--start-line', str(offset), '--lines', '1'], 0,
                predicate=lambda p: p.get('status') == 'ok' and p.get('text') == expected
                    and p.get('source_line') == doc.section.start_line + offset - 1
                    and p.get('revision') == doc.revision)
            report.setdefault('reads', []).append({'doc_id': doc.doc_id, 'revision': doc.revision,
                'source_line': got['source_line'], 'text_sha256': hashlib.sha256(expected.encode()).hexdigest()})
        doc = docs[0]
        invoke('stale revision', ['get', doc.doc_id, '--revision', '0'*64], 4,
               predicate=lambda p: p.get('status') == 'stale' and not p.get('text'))
        invoke('unknown source denied', ['get', 'wiki/Unapproved-Canary-Probe.md#absent', '--revision', '0'*64], 3,
               predicate=lambda p: p.get('status') == 'denied' and not p.get('text'))
        invoke('oversized read rejected', ['get', doc.doc_id, '--revision', doc.revision, '--lines', '201'], 2)
        invoke('rollback remains default-off', ['health'], 2, enabled=False)
        report['input_revisions_after'] = {str(p): sha(p) for p in sorted(set(inputs))}
        report['inputs_unchanged'] = before == report['input_revisions_after']
        report['passed'] = report['inputs_unchanged'] and all(c['passed'] for c in report['checks'])
    except Exception as error:
        report['failure_type'] = type(error).__name__
    finally:
        path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'receipt': str(path), 'passed': report['passed'], 'checks': len(report['checks'])}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registry', type=Path, required=True)
    ap.add_argument('--partition', type=Path, required=True)
    ap.add_argument('--output-root', type=Path, required=True)
    args = ap.parse_args()
    raise SystemExit(verify(args.registry, args.partition, args.output_root))
