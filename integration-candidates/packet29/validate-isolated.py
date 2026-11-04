"""Static core compilation and closed-import actual dispatch checks in scratch only.

Input is a completed git-archive extraction, never the running host checkout.
Dependencies are used by the compiler for static resolution only, not by tests.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent / 'packet28'
DATA = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    assert root.parent == DATA and root.name.startswith('packet29-')
    host = root / 'host'
    assert host.is_dir() and not host.is_symlink()
    assert not (host / '.git').exists(), 'Use an archive, not a live checkout'
    baseline = json.loads((root / 'baseline.json').read_text())
    binding = json.loads((CANDIDATE / 'target-binding.json').read_text())
    assert baseline['host_head'] == binding['host_head']
    target = host / binding['target']
    assert digest(target) == binding['target_sha256']
    assert (host / 'node_modules/typescript/bin/tsc').is_file()
    prefix = sys.argv[2] if len(sys.argv) > 2 else ''
    assert not prefix or (prefix.isalnum() and len(prefix) < 30)
    prefix = prefix + '-' if prefix else ''
    output = root / (prefix + 'validation.json')
    assert not output.exists(), 'Never overwrite a prior validation receipt'
    results = []

    def run(label, args, env=None):
        label = prefix + label
        result = subprocess.run(args, cwd=host, env=env, capture_output=True,
                                text=True, timeout=180)
        stdout = root / (label + '.stdout.log')
        stderr = root / (label + '.stderr.log')
        for path, text in [(stdout, result.stdout), (stderr, result.stderr)]:
            with path.open('x') as handle:
                handle.write(text)
        results.append({'label': label, 'command': args, 'exit_code': result.returncode,
                        'stdout': str(stdout), 'stderr': str(stderr),
                        'stdout_sha256': digest(stdout), 'stderr_sha256': digest(stderr)})
        print(label, 'exit', result.returncode, flush=True)
        return result

    compile_command = ['node', 'node_modules/typescript/bin/tsc', '-p',
                       'tsconfig.core.json', '--noEmit', '--incremental', 'false']
    run('ready-baseline-core-types', compile_command)
    patch = str(CANDIDATE / 'host-custody.patch')
    assert run('patch-check', ['git', 'apply', '--check', patch]).returncode == 0
    assert run('patch-apply', ['git', 'apply', patch]).returncode == 0
    assert digest(target) == binding['candidate_sha256']
    helper = target.with_name('attempt-audience-custody.ts')
    assert digest(helper) == digest(CANDIDATE / helper.name)
    run('patched-core-types', compile_command)
    env = {**os.environ, 'PACKET29_HOST_SOURCE': str(host)}
    tests = ['node', '--experimental-vm-modules', '--test', str(HERE / 'dispatch-boundary.test.mjs')]
    patched = run('patched-dispatch', tests, env)
    assert run('patch-reverse', ['git', 'apply', '--reverse', patch]).returncode == 0
    assert digest(target) == binding['target_sha256'] and not helper.exists()
    # Supply the unchanged helper bytes to the test loader only. Baseline dispatch
    # does not import it. This isolates the call-site negative control.
    helper.write_bytes((CANDIDATE / helper.name).read_bytes())
    negative = run('baseline-dispatch-negative', tests, env)
    helper.unlink()  # Only this script-created scratch file; not a host resource.
    assert digest(target) == binding['target_sha256']
    receipt = {'scope': 'core source typecheck attempt; complete dispatch with synthetic imports',
               'archive': baseline, 'candidate_binding': binding, 'results': results,
               'patched_dispatch_pass': patched.returncode == 0,
               'baseline_negative_rejected': negative.returncode != 0,
               'scratch_target_restored': True,
               'test_sha256': digest(HERE / 'dispatch-boundary.test.mjs'),
               'verifier_sha256': digest(Path(__file__)),
               'limits': ['static dependency tree reused, not frozen', 'no production dependency execution',
                          'not real authority, readers, worker settlement, atomic effects, confinement or write-denial proof']}
    with output.open('x') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    assert patched.returncode == 0, 'Patched dispatch controls failed; retain evidence'
    assert negative.returncode != 0, 'Baseline negative did not discriminate'


if __name__ == '__main__':
    main()
