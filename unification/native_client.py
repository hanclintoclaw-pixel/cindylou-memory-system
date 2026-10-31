"""Bounded synchronous NativeReader; no OpenClaw imports or implicit fallback.

Only trusted local code may select a registry, partition, or child command. Commands
are injectable for hermetic protocol tests, not a remote request parameter.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import threading
import time

from .partition import validate_public
from .policy import AccessContext, StaleReference
from .registry import load_registry

INVALID = 'generation invalid; rebuild required'
ADAPTER = Path(__file__).with_name('native_adapter.mjs')
MAX_RESPONSE = 2_000_000


def validate_generation(registry_path: Path, partition: Path, manifest: dict):
    """Never cache the authority registry, even across the two sides of one call."""
    registry = load_registry(registry_path)
    validate_public(registry, partition, manifest)
    if registry.coverage != manifest['coverage']:
        raise StaleReference(INVALID)
    return registry


class NativeClient:
    def __init__(self, registry_path: Path, partition: Path, *, command=None,
                 timeout: float = 20.0, min_score: float = 0.0):
        if not math.isfinite(timeout) or not 0 < timeout <= 20:
            raise ValueError('timeout must be in (0,20] seconds')
        if type(min_score) not in (int, float) or not math.isfinite(min_score) or min_score < 0:
            raise ValueError('finite nonnegative minimum score required')
        self.registry_path, self.partition = Path(registry_path).absolute(), Path(partition).absolute()
        self.manifest = json.loads((self.partition/'partition.json').read_text())
        self.command = list(command) if command is not None else ['node', str(ADAPTER), str(self.partition), str(self.registry_path), sys.executable]
        self.timeout, self.min_score = timeout, min_score
        self._process = None
        self._request_id = 0
        self._buffer = b''
        self._lock = threading.Lock()
        self._timeouts = self._restarts = 0
        self._closed = self._revoked = self._exhausted = False
        self._startup_failed = False
        self._ready = False

    @property
    def process(self):
        return self._process

    @property
    def restarts(self):
        return self._restarts

    def _envelope(self, status, reason, **fields):
        return {'version': 1, 'status': status, 'results': [], 'coverage': 'partial',
                'backends': [{'id': 'openclaw', 'status': status, 'reason': reason}],
                'reason': reason, **fields}

    def _exchange(self, verb, *, timeout=None, **fields):
        process = self._process
        if process is None or process.poll() is not None:
            raise BrokenPipeError('child unavailable')
        self._request_id += 1
        request_id = self._request_id
        raw = (json.dumps({'id': request_id, 'verb': verb, **fields}, allow_nan=False)+'\n').encode()
        if len(raw) > 65536:
            raise ValueError('request too large')
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        # Nonblocking pipes keep even a child that stops reading within the deadline.
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdin, selectors.EVENT_WRITE)
            sent = 0
            while sent < len(raw):
                remaining = deadline-time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError('native request timed out')
                try:
                    sent += os.write(process.stdin.fileno(), raw[sent:])
                except BlockingIOError:
                    continue
            selector.unregister(process.stdin)
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                while b'\n' in self._buffer:
                    line, self._buffer = self._buffer.split(b'\n', 1)
                    response = json.loads(line)
                    if not isinstance(response, dict):
                        raise ValueError('invalid child response')
                    # A delayed response from a timed-out request cannot answer a later id.
                    if response.get('id') == request_id:
                        if response.get('ok') is not True:
                            raise ValueError('child refused request')
                        return response
                remaining = deadline-time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError('native request timed out')
                try:
                    chunk = os.read(process.stdout.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    raise BrokenPipeError('child exited')
                self._buffer += chunk
                if len(self._buffer) > MAX_RESPONSE:
                    raise ValueError('oversized child response')

    def _start(self):
        if self._process is None:
            env = {k: v for k, v in os.environ.items() if not k.startswith('OPENCLAW_')}
            env.update(OPENCLAW_STATE_DIR=str(self.partition/'state'),
                       OPENCLAW_CONFIG_PATH=str(self.partition/'openclaw.json'))
            self._process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=env, bufsize=0, start_new_session=True)
            for stream in (self._process.stdin, self._process.stdout):
                os.set_blocking(stream.fileno(), False)
            self._buffer = b''
        hello = self._exchange('hello')
        if hello.get('status') != 'ok':
            raise ValueError('native startup refused')
        self._ready = True

    def _stop(self, graceful=False):
        self._ready = False
        process = self._process
        if process is None:
            return
        if graceful and process.poll() is None:
            try:
                self._exchange('shutdown', timeout=min(self.timeout, 0.5))
            except (OSError, ValueError, TimeoutError):
                pass
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # macOS can report EPERM for a process group that just exited.
                # Reap it; never treat a still-running child as successfully stopped.
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
        process.wait(timeout=1)
        for stream in (process.stdin, process.stdout):
            stream.close()
        self._buffer = b''

    def revoke(self):
        """Called by the trusted owner when its bound lease/context becomes stale."""
        # Interrupt a pending read too; its post-I/O context check still runs.
        self._revoked = True
        self._stop()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop(graceful=True)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def _operation(self, verb, ctx, **fields):
        if not self._lock.acquire(blocking=False):
            return self._envelope('unavailable', 'request already in flight')
        try:
            try:
                ctx.check()
            except Exception:
                self.revoke()
                return self._envelope('stale', 'caller lease revoked')
            if self._revoked:
                return self._envelope('stale', 'caller lease revoked')
            if self._closed or self._exhausted or self._startup_failed:
                return self._envelope('unavailable', 'native adapter unavailable')
            try:
                validate_generation(self.registry_path, self.partition, self.manifest)
            except Exception:
                return self._envelope('unavailable', INVALID)
            result = None
            try:
                if self._process is None or not self._ready:
                    try:
                        self._start()
                    except TimeoutError:
                        raise
                    except Exception:
                        self._startup_failed = True
                        self._stop()
                        raise
                result = self._exchange(verb, **fields)
                self._timeouts = 0
            except TimeoutError:
                self._timeouts += 1
                if self._timeouts >= 2:
                    self._stop()
                    if self._restarts == 0:
                        self._restarts = 1
                        self._process = None  # Restart once, lazily on the next valid call.
                        self._timeouts = 0
                    else:
                        self._exhausted = True
                result = self._envelope('unavailable', 'native request timed out')
            except (OSError, ValueError):
                self._stop()
                self._exhausted = True
                result = self._envelope('unavailable', 'native child unavailable')
            # This runs after failures as well as successful I/O. No stale snippets escape.
            try:
                validate_generation(self.registry_path, self.partition, self.manifest)
            except Exception:
                return self._envelope('unavailable', INVALID)
            try:
                ctx.check()
                if self._revoked:
                    raise StaleReference('revoked')
            except Exception:
                self.revoke()
                return self._envelope('stale', 'caller lease revoked')
            if result.get('status') not in {'ok','empty','denied','stale','unavailable'}:
                return self._envelope('unavailable', 'invalid native response status')
            if verb in {'search','get','health'} and result['status'] in {'ok','empty'}:
                backends = result.get('backends')
                if (not isinstance(result.get('results'), list) or not isinstance(backends, list)
                        or not backends or any(not isinstance(b, dict) or b.get('status') != 'ready' for b in backends)):
                    return self._envelope('unavailable', 'native backend not ready')
            # A not-ready backend can never advertise complete registry coverage.
            if result.get('coverage') != self.manifest['coverage'] or any(
                    b.get('status') != 'ready' for b in result.get('backends', [])):
                result['coverage'] = 'partial'
            result.pop('id', None)
            result.pop('ok', None)
            return result
        finally:
            self._lock.release()

    def search(self, query: str, ctx: AccessContext, limit: int = 8) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise ValueError('query must contain 1..4000 characters')
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError('limit must be 1..30')
        return self._operation('search', ctx, query=query, maxResults=limit, minScore=self.min_score)

    def get(self, doc_id: str, ctx: AccessContext, *, revision=None, start_line=1, lines=80):
        if type(start_line) is not int or start_line < 1 or type(lines) is not int or not 1 <= lines <= 200:
            raise ValueError('invalid read bounds')
        if not isinstance(doc_id, str) or len(doc_id) > 4000:
            raise ValueError('invalid document reference')
        return self._operation('get', ctx, doc_id=doc_id, revision=revision, **{'from': start_line, 'lines': lines})

    def health(self, ctx: AccessContext):
        return self._operation('health', ctx)

    def ping(self, ctx: AccessContext):
        return self._operation('ping', ctx)


def _main():
    parser = argparse.ArgumentParser(description='Private adapter generation validation helper')
    parser.add_argument('--validate', nargs=2, metavar=('REGISTRY', 'PARTITION'), required=True)
    args = parser.parse_args()
    try:
        validate_generation(Path(args.validate[0]), Path(args.validate[1]), json.load(sys.stdin))
    except Exception:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
