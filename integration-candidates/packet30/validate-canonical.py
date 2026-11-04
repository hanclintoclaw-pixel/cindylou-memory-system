"""Compare the pinned host's canonical core compiler in fresh private scratch.

No install, code generation, emitted build, provider or production execution.
The compiler pair is copied locally; other dependency links remain explicitly reused.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
DATA = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')
ROOT = DATA / 'packet30-20261104'
PRIOR = DATA / 'packet29-20261104'
LIVE = Path('/Users/hanclaw/claw/openclaw')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    host = ROOT / 'host'
    host.mkdir()
    assert sha(PRIOR / 'host-source.tar') == json.loads((PRIOR / 'closure.json').read_text())['sha256'][str(PRIOR / 'host-source.tar')]
    subprocess.run(['tar', '-xf', str(PRIOR / 'host-source.tar'), '-C', str(host)], check=True)
    modules = host / 'node_modules'
    modules.mkdir()
    links = {}
    # Preserve scoped directory shapes while retaining original static resolutions.
    for source in (LIVE / 'node_modules').iterdir():
        if source.name.startswith('@') and source.is_dir():
            scope = modules / source.name
            scope.mkdir()
            for child in source.iterdir():
                dest = scope / child.name
                dest.symlink_to(child.resolve())
                links[str(dest.relative_to(host))] = str(child.resolve())
        else:
            (modules / source.name).symlink_to(source.resolve())
            links[str((modules / source.name).relative_to(host))] = str(source.resolve())
    # The wrapper rejects external compiler paths: copy compiler and native binary,
    # without changing its boundary implementation or authorizing an escape.
    native = json.loads((LIVE / 'node_modules/typescript/package.json').read_text())
    platform = subprocess.check_output(['node', '-p', 'process.platform+"-"+process.arch'], text=True).strip()
    compiler_dirs = ['typescript', '@typescript/typescript-' + platform]
    copied = {}
    for name in compiler_dirs:
        source = (LIVE / 'node_modules' / name).resolve()
        if not source.exists():
            # pnpm's platform package is owned beside the compiler, not top-level.
            source = (LIVE / 'node_modules/typescript').resolve().parent / name
            source = source.resolve()
        dest = modules / name
        if dest.is_symlink():
            dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, dest)
        copied.update({str(p.relative_to(host)): sha(p) for p in dest.rglob('*') if p.is_file()})
        links.pop(str(dest.relative_to(host)), None)
    supplement = json.loads((PRIOR / 'static-environment-supplement.json').read_text())
    for relative, expected in supplement['generated_type_source_sha256'].items():
        source = PRIOR / 'host' / relative
        assert sha(source) == expected
        dest = host / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    for item in supplement['static_dependency_links']:
        dest = host / item['path']
        dest.symlink_to(item['target'])
        links[item['path']] = item['target']
    # Match the generator's content fingerprint so ensureKyselyTypes returns
    # before importing node:sqlite. No SQL execution or generator invocation.
    h = hashlib.sha256((host / 'scripts/generate-kysely-types.mts').read_bytes())
    for name in ['openclaw-state', 'openclaw-agent']:
        h.update(name.encode()); h.update(b'\0')
        h.update((host / 'src/state' / (name + '-schema.sql')).read_bytes()); h.update(b'\0')
        h.update((host / '.artifacts/kysely' / (name + '-db.generated.ts')).read_bytes())
    (host / '.artifacts/kysely/inputs.sha256').write_text(h.hexdigest())
    binding = json.loads((HERE.parent / 'packet28/target-binding.json').read_text())
    target = host / binding['target']
    live_before = sha(LIVE / binding['target'])
    assert sha(target) == binding['target_sha256'] == live_before
    assert not (host / '.git').exists() and not modules.is_symlink()
    environment = {'compiler_version': native['version'], 'copied_compiler_sha256': copied,
                   'static_dependency_links': links,
                   'generated_inputs': supplement['generated_type_source_sha256'],
                   'generator_stamp': h.hexdigest(),
                   'limit': 'compiler copied locally; remaining static dependencies reused, not frozen'}
    (ROOT / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
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
    baseline = run('canonical-baseline', canonical)
    patches = [HERE.parent / 'packet28/host-custody.patch', HERE.parent / 'packet29/host-custody-type-fix.patch']
    applied = []
    try:
        for i, patch in enumerate(patches):
            assert run('apply-' + str(i), ['git', 'apply', str(patch)]).returncode == 0
            applied.append(patch)
        assert sha(target) == json.loads((HERE.parent / 'packet29/type-fix-binding.json').read_text())['corrected_candidate_sha256']
        patched = run('canonical-candidate', canonical)
        declarations = run('explicit-declarations-candidate', canonical + ['--declaration', 'true'])
    finally:
        for i, patch in enumerate(reversed(applied)):
            assert run('reverse-' + str(i), ['git', 'apply', '--reverse', str(patch)]).returncode == 0
    assert sha(target) == binding['target_sha256'] and not target.with_name('attempt-audience-custody.ts').exists()
    assert sha(LIVE / binding['target']) == live_before
    assert all(sha(host / p) == expected for p, expected in copied.items())
    assert all(sha(host / p) == expected for p, expected in supplement['generated_type_source_sha256'].items())
    diagnostic_codes = Counter(re.findall(r'error (TS\d+)', declarations.stdout))
    receipt = {'results': results, 'canonical_baseline_pass': baseline.returncode == 0,
               'canonical_candidate_pass': patched.returncode == 0,
               'explicit_declarations_pass': declarations.returncode == 0,
               'explicit_declaration_diagnostics': dict(diagnostic_codes),
               'explicit_declaration_status': ('passed' if declarations.returncode == 0 else
                                               'timeout' if 'no completion after' in declarations.stderr else
                                               'failed'),
               'scratch_restored': True, 'live_target_unchanged': True,
               'environment_sha256': sha(ROOT / 'environment.json'),
               'validator_sha256': sha(Path(__file__)),
               'policy_sha256': sha(host / 'scripts/lib/local-check-runtime.mts'),
               'scope': 'canonical core static check, not UI/extensions/tests/build or live integration'}
    with (ROOT / 'validation.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    assert baseline.returncode == 0 and patched.returncode == 0
    # Successful canonical checks do not close a failed/timeout declaration gate.
    # Compare declarations only against a future same-checkout baseline, never
    # against diagnostic messages containing another checkout's absolute paths.


if __name__ == '__main__':
    main()
