"""Validate a staged patch using scratch files only; never apply to the host."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
HOST = Path('/Users/hanclaw/claw/openclaw')
DATA = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify():
    binding = json.loads((HERE / 'target-binding.json').read_text())
    source = HOST / binding['target']
    original = source.read_bytes()
    assert sha(original) == binding['target_sha256'], 'Host source drift; do not rebase silently'
    results = []

    def run(args, cwd):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        results.append({'command': args, 'exit_code': result.returncode,
                        'stdout': result.stdout, 'stderr': result.stderr})
        assert result.returncode == 0, result.stderr

    with tempfile.TemporaryDirectory(prefix='packet28-scratch-', dir=DATA) as directory:
        scratch = Path(directory)
        target = scratch / binding['target']
        target.parent.mkdir(parents=True)
        target.write_bytes(original)
        patch = str(HERE / 'host-custody.patch')
        run(['git', 'apply', '--check', patch], scratch)
        run(['git', 'apply', patch], scratch)
        assert sha(target.read_bytes()) == binding['candidate_sha256']
        helper = target.with_name('attempt-audience-custody.ts')
        assert helper.read_bytes() == (HERE / helper.name).read_bytes()
        run(['node', '--check', str(target)], scratch)
        run(['node', '--check', str(helper)], scratch)
        run(['git', 'apply', '--reverse', '--check', patch], scratch)
        run(['git', 'apply', '--reverse', patch], scratch)
        assert target.read_bytes() == original
        assert not helper.exists()
    run(['node', '--test', str(HERE / 'test-attempt-audience-custody.mjs')], HERE)
    assert source.read_bytes() == original
    return {'scope': 'scratch patch application/roundtrip and syntax; candidate helper tests only',
            'host_source_unchanged': True, 'target_sha256': sha(original),
            'candidate_files': {p.name: sha(p.read_bytes()) for p in HERE.iterdir()
                                if p.is_file()},
            'results': results,
            'not_verified': ['whole-host typecheck', 'actual dispatch execution',
                            'reader integration', 'worker settlement', 'effect fences',
                            'active identity', 'confinement', 'production write denial']}


if __name__ == '__main__':
    import sys
    output = Path(sys.argv[1])
    with output.open('x') as handle:
        json.dump(verify(), handle, indent=2)
        handle.write('\n')
    print(f'Verified scratch patch roundtrip, syntax and candidate helper tests; receipt: {output}')
