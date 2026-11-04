"""Opt-in Darwin sandbox proof for fixed synthetic children only.

Not a general command runner. No real reader lane or production target input is
accepted. A successful receipt is not host authority or production isolation.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import signal
import subprocess
import sys

from .isolation import canonical, Rejected

SANDBOX = Path('/usr/bin/sandbox-exec')

# This fixed payload only accesses parent-created synthetic fixtures. Fork/spawn
# success is a failed control, and any unexpected child is immediately reaped.
CHILD = r'''
import errno, json, os, subprocess, sys, time
from pathlib import Path
w, p, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
if mode == 'timeout':
    print('started', flush=True)
    time.sleep(30)
    raise SystemExit(0)
results = []
def attempt(name, fn):
    try:
        fn()
    except OSError as e:
        results.append({'name': name, 'denied': e.errno in (errno.EPERM, errno.EACCES), 'errno': e.errno})
    else:
        results.append({'name': name, 'denied': False})
(w/'allowed.txt').write_text('synthetic-positive\n')
attempt('overwrite', lambda: (p/'sentinel.txt').write_text('changed'))
attempt('create', lambda: (p/'new.txt').write_text('changed'))
attempt('unlink', lambda: (p/'sentinel.txt').unlink())
attempt('rename', lambda: (p/'sentinel.txt').rename(w/'stolen.txt'))
attempt('replace', lambda: os.replace(w/'allowed.txt', p/'sentinel.txt'))
attempt('chmod', lambda: (p/'sentinel.txt').chmod(0o777))
(w/'alias').symlink_to(p/'sentinel.txt')
attempt('symlink-write', lambda: (w/'alias').write_text('changed'))
attempt('hardlink', lambda: os.link(p/'sentinel.txt', w/'hardlink'))
attempt('sidecar', lambda: (p/'synthetic.sqlite-wal').write_text('changed'))
def fork():
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
attempt('fork', fork)
def spawn():
    child = subprocess.Popen(['/usr/bin/true'], start_new_session=True, close_fds=True)
    child.wait(timeout=2)
attempt('spawn-detached', spawn)
print(json.dumps({'controls':results, 'allowed_write':(w/'allowed.txt').read_text() == 'synthetic-positive\n'}))
'''


def profile_for(writable):
    """Deny writes elsewhere and deny new descendants; do not run untrusted code.

    Seatbelt applies to syscalls, unlike Python path guards. Default reads/system
    access remain allowed for interpreter startup. This is NOT confidentiality
    isolation; it is scoped synthetic write/fork-denial evidence only.
    """
    literal = json.dumps(str(writable))
    return ('(version 1)\n(allow default)\n'
            '(deny file-write*)\n'
            f'(allow file-write* (subpath {literal}))\n'
            '(deny file-link)\n(deny network*)\n(deny process-fork)\n')


def _identity(path):
    info = path.stat()
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
            'mode': info.st_mode, 'inode': info.st_ino}


def _run(profile, writable, protected, mode, timeout):
    proc = subprocess.Popen([str(SANDBOX), '-f', str(profile),
        str(Path(sys.executable).resolve()), '-I', '-S', '-B', '-c', CHILD,
        str(writable), str(protected), mode], cwd=writable, env={},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        close_fds=True, start_new_session=True, text=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        # The profile forbids descendants. The process group is defense-in-depth,
        # not proof that a detached arbitrary descendant could not escape it.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate(timeout=5)
    return {'returncode': proc.returncode, 'timed_out': timed_out,
            'direct_child_reaped': proc.poll() is not None,
            'stdout': stdout, 'stderr': stderr}


def run_synthetic_confinement(parent, *, enabled=False, lane='synthetic'):
    """Create fresh synthetic targets; never accept caller-provided targets/code.

    Unsupported/failed platform proof returns unavailable, never unsandboxed
    fallback. Keep all artifacts for review, including failed controls.
    """
    base = {'kind': 'synthetic-platform-confinement-only',
            'real_reader_execution': False, 'private_native_available': False,
            'host_authority_proven': False, 'production_write_denial_proven': False,
            'compiled_provider_equivalence_proven': False}
    if not enabled or lane != 'synthetic':
        return {**base, 'status': 'unavailable', 'reason': 'default-off-or-real-lane'}
    if platform.system() != 'Darwin' or not SANDBOX.is_file():
        return {**base, 'status': 'unavailable', 'reason': 'platform-control-unavailable'}
    parent = canonical(parent)
    if not parent.is_dir() or parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o777 != 0o700:
        raise Rejected('owned 0700 scratch parent required')
    root = parent / ('confinement-' + secrets.token_hex(12))
    root.mkdir(mode=0o700)
    writable, protected = root/'writable', root/'protected'
    writable.mkdir(mode=0o700)
    protected.mkdir(mode=0o700)
    sentinel = protected/'sentinel.txt'
    sentinel.write_text('synthetic-protected-sentinel\n')
    sentinel.chmod(0o600)
    before = _identity(sentinel)
    profile = root/'synthetic.sb'
    profile.write_text(profile_for(writable))
    profile.chmod(0o600)
    try:
        active = _run(profile, writable, protected, 'controls', 10)
    except OSError as error:
        active = {'returncode': None, 'timed_out': False,
                  'direct_child_reaped': False, 'stdout': '',
                  'stderr': type(error).__name__ + ': ' + str(error)}
    try:
        controls = json.loads(active['stdout']) if active['returncode'] == 0 else {}
    except json.JSONDecodeError:
        controls = {}
    expected = {'overwrite', 'create', 'unlink', 'rename', 'replace', 'chmod',
                'symlink-write', 'hardlink', 'sidecar', 'fork', 'spawn-detached'}
    entries = controls.get('controls', [])
    denial = (len(entries) == len(expected)
              and {e.get('name') for e in entries} == expected
              and all(e.get('denied') is True for e in entries))
    preserved = sentinel.exists() and _identity(sentinel) == before and list(protected.iterdir()) == [sentinel]
    # Never proceed after a failed enforcement control. Fork denial is required
    # before timeout/settlement gets exercised with a second fixed no-fork child.
    timeout = None
    if denial and preserved and controls.get('allowed_write') is True and active['direct_child_reaped']:
        timeout = _run(profile, writable, protected, 'timeout', 0.5)
    settled = bool(timeout and timeout['timed_out'] and timeout['direct_child_reaped']
                   and timeout['returncode'] == -signal.SIGKILL and 'started' in timeout['stdout'])
    preserved = (preserved and sentinel.exists() and _identity(sentinel) == before
                 and list(protected.iterdir()) == [sentinel])
    settled = settled and preserved
    result = {**base, 'status': 'synthetic-proof-passed' if settled else 'unavailable',
        'reason': 'bounded-synthetic-controls-only' if settled else 'platform-proof-failed',
        'platform': platform.system(), 'scratch_root': str(root),
        'sandbox_binary': str(SANDBOX), 'sandbox_binary_sha256': _identity(SANDBOX)['sha256'],
        'python_binary': str(Path(sys.executable).resolve()),
        'python_binary_sha256': _identity(Path(sys.executable).resolve())['sha256'],
        'child_payload_sha256': hashlib.sha256(CHILD.encode()).hexdigest(),
        'profile_sha256': _identity(profile)['sha256'], 'active_control': active,
        'controls': controls, 'protected_before': before,
        'synthetic_protected_preserved': preserved,
        'fork_and_detached_spawn_denied': denial,
        'timeout_control': timeout, 'timeout_child_settled': settled,
        'descendant_strategy': 'kernel-deny-creation; no arbitrary descendant runner',
        'limitations': ['No real targets/readers/providers/DBs executed or opened',
            'No confidentiality/read-denial proof; default reads and system/IPC operations remain allowed',
            'Configured network denial is not an exercised network-isolation proof',
            'No uncontrolled or detached descendants allowed; fork/spawn were denied, not supervised after creation',
            'No host caller authority or compiled provider/worker identity proof',
            'No production write-denial proof or arbitrary descendant containment',
            'No retrieval/answer/latency/migration completion evidence']}
    (root/'receipt.json').write_text(json.dumps(result, indent=2)+'\n')
    return result
