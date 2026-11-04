"""Validate the uninstalled admission-only executor scaffold; no real readers.

Reuse Packet30's restored static compiler environment, not its test results.
The exact same scratch tree is checked before and after candidate insertion.
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DATA = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')
OUT = DATA / 'packet31-20261104'
HOST = DATA / 'packet30-20261104/host'
LIVE = Path('/Users/hanclaw/claw/openclaw')
TARGET = 'src/plugins/memory-invocation-executor.ts'


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    os.umask(0o077)
    assert not (HOST / TARGET).exists() and not (LIVE / TARGET).exists()
    assert subprocess.check_output(['git', '-C', str(LIVE), 'rev-parse', 'HEAD'], text=True).strip() == '4d94a9fac61f2e83331a09df18ad35cdfb1faf5c'
    prior = json.loads((DATA / 'packet30-20261104/environment.json').read_text())
    # Hash the existing compiler copies, generated declarations and their content
    # stamp; reused dependency links remain non-frozen and not runtime identity.
    selected = [p for p in (HOST / 'node_modules/typescript').rglob('*') if p.is_file()]
    selected += [p for p in (HOST / 'node_modules/@typescript/typescript-darwin-arm64').rglob('*') if p.is_file()]
    selected += list((HOST / '.artifacts/kysely').glob('*'))
    selected = [p for p in selected if p.is_file()]
    static_before = {str(p): sha(p) for p in selected}
    source_paths = ['src/agents/admitted-run-context.ts', 'src/plugins/memory-audience.ts',
                    'src/plugins/memory-provider-types.ts', 'src/agents/embedded-agent-runner/run/run-attempt-dispatch.ts']
    live_before = {p: sha(LIVE / p) for p in source_paths}
    assert all(sha(HOST / p) == digest for p, digest in live_before.items())
    before = {str(p): sha(p) for p in HERE.iterdir() if p.is_file()}
    results = []

    def run(label, command, cwd=HOST, extra_env=None):
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180,
                                env={**os.environ, 'OPENCLAW_TSGO_TIMEOUT_MS': '120000', **(extra_env or {})})
        streams = {}
        for stream in ('stdout', 'stderr'):
            p = OUT / f'{label}.{stream}.log'
            with p.open('x') as f:
                f.write(getattr(result, stream))
            streams[stream] = {'path': str(p), 'sha256': sha(p)}
        results.append({'label': label, 'exit_code': result.returncode, 'command': command, **streams})
        print(label, result.returncode, flush=True)
        return result

    node = ['node', '--experimental-vm-modules', '--test', str(HERE / 'executor-boundary.test.mjs')]
    unit = run('executor-controls', node)
    mutants = [run('negative-' + m, node, extra_env={'PACKET31_MUTANT': m}) for m in ('omit-default-off', 'admit-copy')]
    canonical = ['node', 'scripts/run-tsgo.mjs', '-p', 'tsconfig.core.json', '--noEmit', '--incremental', 'false']
    baseline = run('canonical-baseline', canonical)
    patches = [HERE.parent / 'packet28/host-custody.patch', HERE.parent / 'packet29/host-custody-type-fix.patch', HERE / 'host-executor.patch']
    applied = []
    try:
        for i, patch in enumerate(patches):
            assert run(f'apply-{i}', ['git', 'apply', str(patch)]).returncode == 0
            applied.append(patch)
        assert sha(HOST / TARGET) == sha(HERE / 'memory-invocation-executor.ts')
        candidate = run('canonical-candidate', canonical)
    finally:
        for i, patch in enumerate(reversed(applied)):
            assert run(f'reverse-{i}', ['git', 'apply', '--reverse', str(patch)]).returncode == 0
    assert not (HOST / TARGET).exists()
    assert not (HOST / 'src/agents/embedded-agent-runner/run/attempt-audience-custody.ts').exists()
    assert all(sha(HOST / p) == digest and sha(LIVE / p) == digest for p, digest in live_before.items())
    assert all(sha(Path(p)) == digest for p, digest in static_before.items())
    assert all(sha(Path(p)) == digest for p, digest in before.items())
    receipt = {'results': results, 'candidate_source_sha256': sha(HERE / 'memory-invocation-executor.ts'),
               'executed_validator_sha256': sha(Path(__file__)), 'source_bindings': live_before,
               'static_input_bindings': static_before, 'prior_environment_sha256': sha(DATA / 'packet30-20261104/environment.json'),
               'controls_pass': unit.returncode == 0, 'negative_controls_fail': all(r.returncode == 1 for r in mutants),
               'canonical_baseline_pass': baseline.returncode == 0, 'canonical_candidate_pass': candidate.returncode == 0,
               'scratch_restored': True, 'installed_selected_sources_unchanged': True,
               'limits': 'Admission-only scaffold. VM policy override is synthetic; all reads unavailable. No dispatch hook, real admission issuance, effect protocol, active identity, confinement, resource settlement or declaration acceptance.'}
    with (OUT / 'validation.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    assert all(receipt[k] for k in ('controls_pass', 'negative_controls_fail', 'canonical_baseline_pass', 'canonical_candidate_pass'))


if __name__ == '__main__':
    main()
