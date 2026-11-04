"""Validate the two-line type correction; preserve earlier failing receipts."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'packet28'
DATA = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    assert root.parent == DATA and root.name.startswith('packet29-')
    host = root / 'host'
    assert not host.is_symlink() and not (host / '.git').exists()
    parent = json.loads((root / 'supplemented-validation.json').read_text())
    assert parent['scratch_target_restored'] and parent['patched_dispatch_pass']
    binding = json.loads((PARENT / 'target-binding.json').read_text())
    fix = json.loads((HERE / 'type-fix-binding.json').read_text())
    target = host / binding['target']
    assert sha(target) == binding['target_sha256']
    output = root / 'corrected-validation.json'
    assert not output.exists()
    results = []

    def run(label, command, env=None):
        result = subprocess.run(command, cwd=host, env=env, capture_output=True,
                                text=True, timeout=180)
        logs = {}
        for stream in ['stdout', 'stderr']:
            path = root / ('corrected-' + label + '.' + stream + '.log')
            with path.open('x') as handle:
                handle.write(getattr(result, stream))
            logs[stream] = {'path': str(path), 'sha256': sha(path)}
        results.append({'label': label, 'command': command, 'exit_code': result.returncode, **logs})
        print(label, 'exit', result.returncode, flush=True)
        return result

    patches = [PARENT / 'host-custody.patch', HERE / 'host-custody-type-fix.patch']
    for index, patch in enumerate(patches):
        assert run(f'apply-{index}', ['git', 'apply', str(patch)]).returncode == 0
    assert sha(target) == fix['corrected_candidate_sha256']
    compile_command = ['node', 'node_modules/typescript/bin/tsc', '-p', 'tsconfig.core.json',
                       '--noEmit', '--incremental', 'false']
    full = run('core-config-types', compile_command)
    semantic = run('core-semantic-types', compile_command + ['--declaration', 'false'])
    env = {**os.environ, 'PACKET29_HOST_SOURCE': str(host)}
    controls = run('dispatch', ['node', '--experimental-vm-modules', '--test',
                               str(HERE / 'dispatch-boundary.test.mjs')], env)
    for index, patch in enumerate(reversed(patches)):
        assert run(f'reverse-{index}', ['git', 'apply', '--reverse', str(patch)]).returncode == 0
    assert sha(target) == binding['target_sha256']
    assert not target.with_name('attempt-audience-custody.ts').exists()
    baseline_path = root / 'supplemented-ready-baseline-core-types.stdout.log'
    baseline = baseline_path.read_text()
    normalize = lambda text: Counter(re.sub(r'\(\d+,\d+\)', '(line,col)', line)
                                    for line in text.splitlines())
    added = list((normalize(full.stdout) - normalize(baseline)).elements())
    removed = list((normalize(baseline) - normalize(full.stdout)).elements())
    receipt = {
        'scope': 'uninstalled type correction; actual dispatch with synthetic imports',
        'parent_receipt_sha256': sha(root / 'supplemented-validation.json'),
        'baseline_log_sha256': sha(baseline_path),
        'corrected_binding': fix, 'results': results,
        'full_core_config_pass': full.returncode == 0,
        'baseline_core_diagnostics': len(re.findall(r'error TS\d+', baseline)),
        'corrected_core_diagnostics': len(re.findall(r'error TS\d+', full.stdout)),
        'new_normalized_diagnostic_lines': added, 'removed_normalized_diagnostic_lines': removed,
        'semantic_only_core_pass': semantic.returncode == 0,
        'semantic_only_limit': 'declaration=false is supplemental; source tsconfig full gate remains separate',
        'dispatch_pass': controls.returncode == 0, 'scratch_restored': True,
        'source_sha256': {str(p): sha(p) for p in HERE.iterdir() if p.is_file()},
        'limitations': ['not whole-host clean typecheck', 'static dependency tree reused, not frozen',
                        'not active runtime/build identity', 'no real reader or authority integration'],
    }
    with output.open('x') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    assert not added and not removed, 'Full-config diagnostic set changed; review evidence'
    assert semantic.returncode == 0 and controls.returncode == 0


if __name__ == '__main__':
    main()
