"""Verify an uncorrected canonical compiler negative.

Run only after validate-canonical.py has restored its scratch target. The older
declaration-enabled run may remain failed/timed out. This control does not repeat
or waive that gate; it checks that canonical policy still catches the type defect.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification/packet30-20261104')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    host = ROOT / 'host'
    first = json.loads((ROOT / 'validation.json').read_text())
    assert first['canonical_baseline_pass'] and first['canonical_candidate_pass'] and first['scratch_restored']
    binding = json.loads((HERE.parent / 'packet28/target-binding.json').read_text())
    target = host / binding['target']
    assert sha(target) == binding['target_sha256']
    results = []

    def run(label, command):
        result = subprocess.run(command, cwd=host, capture_output=True, text=True, timeout=180,
                                env={**os.environ, 'OPENCLAW_TSGO_TIMEOUT_MS': '120000'})
        logs = {}
        for stream in ['stdout', 'stderr']:
            p = ROOT / (label + '.' + stream + '.log')
            with p.open('x') as f:
                f.write(getattr(result, stream))
            logs[stream] = {'path': str(p), 'sha256': sha(p)}
        results.append({'label': label, 'command': command, 'exit_code': result.returncode, **logs})
        print(label, result.returncode, flush=True)
        return result

    canonical = ['node', 'scripts/run-tsgo.mjs', '-p', 'tsconfig.core.json', '--noEmit', '--incremental', 'false']
    patch = HERE.parent / 'packet28/host-custody.patch'
    assert run('control-apply', ['git', 'apply', str(patch)]).returncode == 0
    try:
        negative = run('control-uncorrected-canonical', canonical)
    finally:
        assert run('control-reverse', ['git', 'apply', '--reverse', str(patch)]).returncode == 0
    assert sha(target) == binding['target_sha256'] and not target.with_name('attempt-audience-custody.ts').exists()
    codes = Counter(re.findall(r'error (TS\d+)', negative.stdout))
    receipt = {'results': results, 'first_validation_sha256': sha(ROOT / 'validation.json'),
               'uncorrected_canonical_codes': dict(codes),
               'canonical_negative_discriminates': negative.returncode == 2 and codes == {'TS2322': 1, 'TS2345': 1},
               'scratch_restored': True, 'validator_sha256': sha(Path(__file__)),
               'limits': 'static compiler evidence only; no declaration acceptance or live integration'}
    with (ROOT / 'controls.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    assert receipt['canonical_negative_discriminates']


if __name__ == '__main__':
    main()
