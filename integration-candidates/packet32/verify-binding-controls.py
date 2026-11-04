"""Repeat strengthened pair controls, preserving the original executed tests.

No compiler rerun: candidate source/patches are unchanged from validation.json.
No production dependency/provider import. Always reverse the scratch patches.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DATA = Path('/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification')
OUT = DATA / 'packet32-20261104'
HOST = DATA / 'packet30-20261104/host'
LIVE = Path('/Users/hanclaw/claw/openclaw')
TARGET = 'src/agents/embedded-agent-runner/run/attempt-memory-binding.ts'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    os.umask(0o077)
    prior = json.loads((OUT / 'validation.json').read_text())
    assert all(prior[k] for k in ('canonical_baseline_pass', 'canonical_candidate_pass', 'scratch_restored'))
    assert sha(HERE / 'attempt-memory-binding.ts') == prior['candidate_source_sha256']
    assert sha(OUT / 'initial-executed-validate-binding.py') == prior['executed_validator_sha256']
    assert not (HOST / TARGET).exists() and not (LIVE / TARGET).exists()
    assert all(sha(HOST / p) == h and sha(LIVE / p) == h for p,h in prior['source_bindings'].items())
    assert all(sha(p) == h for p,h in prior['static_input_bindings'].items())
    before = {str(p): sha(p) for p in HERE.iterdir() if p.is_file()}
    rows = []
    def run(label, cmd, env=None):
        result = subprocess.run(cmd, cwd=HOST, capture_output=True, timeout=30,
                                env={**os.environ, **(env or {})})
        streams = {}
        for stream in ('stdout', 'stderr'):
            p = OUT / ('final-' + label + '.' + stream + '.log')
            with p.open('xb') as f: f.write(getattr(result,stream))
            streams[stream] = {'path':str(p), 'sha256':sha(p)}
        rows.append({'label':label, 'command':cmd, 'exit_code':result.returncode, **streams})
        return result
    patches = [HERE.parent/'packet28/host-custody.patch', HERE.parent/'packet29/host-custody-type-fix.patch', HERE/'host-binding.patch']
    applied = []
    try:
        for i,p in enumerate(patches):
            assert run('apply-'+str(i), ['git','apply',str(p)]).returncode == 0
            applied.append(p)
        assert sha(HOST / TARGET) == prior['candidate_source_sha256']
        node=['node','--experimental-vm-modules','--test',str(HERE/'dispatch-binding.test.mjs')]
        env={'PACKET32_HOST_SOURCE':str(HOST)}
        assert run('enabled',node,env).returncode == 0
        assert run('disabled',node,{**env,'PACKET32_DISABLED':'1'}).returncode == 0
        for mutant in ('cross-pair','retain-binding'):
            r=run(mutant,node,{**env,'PACKET32_MUTANT':mutant})
            assert r.returncode == 1
            assert b'Missing expected exception' in r.stdout
            assert b'SyntaxError' not in r.stdout and b'SyntaxError' not in r.stderr
        assert run('supplement',['node','--experimental-vm-modules','--test',str(HERE/'binding-rejection.test.mjs')]).returncode == 0
    finally:
        for i,p in enumerate(reversed(applied)):
            assert run('reverse-'+str(i),['git','apply','--reverse',str(p)]).returncode == 0
    assert not (HOST/TARGET).exists()
    assert not (HOST/'src/agents/embedded-agent-runner/run/attempt-audience-custody.ts').exists()
    assert all(sha(HOST/p)==h and sha(LIVE/p)==h for p,h in prior['source_bindings'].items())
    assert all(sha(p)==h for p,h in prior['static_input_bindings'].items())
    assert all(sha(p)==h for p,h in before.items())
    receipt={'prior_validation_sha256':sha(OUT/'validation.json'),'source_sha256':before,
             'results':rows,'restored':True,'selected_installed_sources_unchanged':True,
             'scope':'Same candidate; strengthened synthetic current-pair mocks. No new compiler/declaration or live integration clearance.'}
    with (OUT/'final-controls.json').open('x') as f: json.dump(receipt,f,indent=2);f.write('\n')
    print('Final enabled/disabled/rejection controls pass; both mutants rejected; scratch restored.')
if __name__=='__main__': main()
