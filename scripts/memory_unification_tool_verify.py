#!/usr/bin/env python3
"""Verify real stdio tool -> approved live API, without changing its lifecycle.

Private receipt stores hashes/statuses/timings, not source passages or tokens.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from unification.policy import AccessContext
from unification.registry import load_registry


def verify(state_path, output_root, caller='stdio', code_root=ROOT, gateway_session=None):
    os.umask(0o077)
    output = output_root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    receipt = output/'tool-verification.private.json'
    report = {'version': 1, 'scope': caller+' isolated tool to approved API; not live host discovery/admission',
              'passed': False, 'coverage': 'partial', 'checks': [],
              'latency_scope': 'fresh tool process plus HTTP plus per-request native lifecycle; not warm p95',
              'native_runtime_state': 'isolated partition index/recall state may update'}
    if caller == 'gateway':
        if not gateway_session:
            raise ValueError('gateway caller requires exact target session')
        report['scope'] = 'actual live Gateway operator RPC tool invocation; not a Discord model turn'
        report['rollback_scope'] = 'live config disable/re-enable verified in separate deployment receipt'

    def check(label, passed, **fields):
        report['checks'].append({'label': label, 'passed': bool(passed), **fields})
        if not passed:
            raise RuntimeError('tool verification check failed')

    try:
        state = json.loads(state_path.read_text())
        deployment = json.loads(Path(state['artifacts']['api_live_deployment']).read_text())
        active = state['active_processes'][0]
        port = deployment['port']
        token_file = Path(deployment['runtime'])/'route-token'
        release = Path(deployment['release'])
        pid = active['pid']
        identity = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, check=True).stdout
        check('recorded API process is pinned release', str(release/'launch.py') in identity and '--enable-canary' in identity)
        sockets = subprocess.run(['lsof', '-nP', '-a', '-p', str(pid), '-iTCP', '-sTCP:LISTEN'], capture_output=True, text=True, check=True).stdout
        check('recorded process listens on fixed IPv4 loopback', f'127.0.0.1:{port} (LISTEN)' in sockets and '*:' not in sockets)
        registry = Path(state['artifacts']['reviewed_pilot_registry'])
        partition = Path(state['artifacts']['reviewed_pilot_partition'])
        docs = list(load_registry(registry).documents(AccessContext(), 'campaign'))
        inputs = list((code_root/'unification').glob('*.py')) + list((code_root/'unification').glob('*.mjs'))
        inputs += list((code_root/'integrations/openclaw-memory-canary').glob('*'))
        inputs += [code_root/'scripts/memory_unification_tool_plugin_probe.mjs']
        if (code_root/'release.json').exists():
            release_manifest = json.loads((code_root/'release.json').read_text())
            check('released module hashes match manifest', all(
                hashlib.sha256((code_root/name).read_bytes()).hexdigest() == digest
                for name, digest in release_manifest['sha256'].items()))
            inputs += [code_root/'release.json']
            report['release_commit'] = release_manifest['commit']
        inputs += [Path(__file__), registry, partition, partition.parent/'openclaw.json']
        inputs += [doc.source.root/doc.doc_id.split('#')[0].split('/', 1)[1] for doc in docs]
        # Compare the same selected existing callers/configs, not every runtime file.
        inputs += [Path('/Users/hanclaw/.local/bin/cindylou'),
                   Path('/Users/hanclaw/claw/projects/cindylou/memory-system/05_serving/memory_api_server.py'),
                   Path('/Users/hanclaw/claw/projects/discord_voice_patch/voice_chat.py'),
                   Path('/Users/hanclaw/.openclaw/openclaw.json')]

        def hashes():
            return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs))}

        report['inputs_before'] = hashes()
        base = [sys.executable, '-I', '-c',
                'import sys;sys.path.insert(0,sys.argv[1]);from unification.canary_tool import main;raise SystemExit(main(sys.argv[2:]))',
                str(code_root), '--token-file', str(token_file), '--port', str(port)]

        def call(label, request, expected, *, enabled=True, predicate=lambda unused: True):
            start = time.monotonic()
            command = (['node', str(code_root/'scripts/memory_unification_tool_plugin_probe.mjs'),
                        str(token_file), str(port), 'enabled' if enabled else 'disabled'] if caller == 'plugin'
                       else base+(['--enable-canary'] if enabled else []))
            if caller == 'gateway':
                command = ['openclaw', 'gateway', 'call', 'tools.invoke', '--params', json.dumps({
                    'name': 'cindylou_memory_canary', 'agentId': 'cindylou',
                    'sessionKey': gateway_session, 'args': request}), '--timeout', '25000', '--json']
            run = subprocess.run(command,
                                 input=json.dumps(request).encode(), cwd='/', capture_output=True, timeout=35)
            payload = json.loads(run.stdout)
            if caller == 'gateway':
                if payload.get('ok') is not True or payload.get('source') != 'plugin':
                    raise RuntimeError('Gateway did not admit plugin invocation')
                payload = payload['output']
            details = payload['details']
            check(label, details['status'] == expected and predicate(details)
                  and json.loads(payload['content'][0]['text']) == details
                  and payload['isError'] == (expected not in ['ok', 'empty'])
                  and run.returncode == (0 if caller == 'gateway' else
                      {'disabled': 2, 'invalid_request': 2, 'denied': 3,
                       'stale': 4, 'unavailable': 5}.get(expected, 0)),
                  status=details['status'], exit_code=run.returncode,
                  response_sha256=hashlib.sha256(run.stdout).hexdigest(), elapsed_s=time.monotonic()-start)
            return details

        if caller != 'gateway':
            call('disabled before enabled use', {'operation': 'health'}, 'disabled', enabled=False)
        call('actual tool authenticated health', {'operation': 'health'}, 'ok')
        for doc in docs:
            query = Path(doc.doc_id.split('#')[0]).stem.replace('-', ' ')
            found = call('tool search '+doc.doc_id, {'operation': 'search', 'query': query}, 'ok',
                         predicate=lambda p: any(h['doc_id'] == doc.doc_id and h['revision'] == doc.revision for h in p['results']))
            hit = next(h for h in found['results'] if h['doc_id'] == doc.doc_id)
            offset = 2 if len(doc.content.splitlines()) > 1 else 1
            expected = '\n'.join(doc.content.splitlines()[offset-1:offset])[:16000]
            call('tool exact bounded read '+doc.doc_id,
                 {'operation': 'get', 'doc_id': hit['doc_id'], 'revision': hit['revision'],
                  'start_line': offset, 'lines': 1}, 'ok',
                 predicate=lambda p: p['text'] == expected and p['source_line'] == doc.section.start_line+offset-1
                 and p['citation'] == hit['citation'] and p['claim_status'] == hit['claim_status']
                 and p['evidence_group'] == hit['evidence_group'] and 'excerpt' not in p)
        call('tool stale revision preserved', {'operation': 'get', 'doc_id': docs[0].doc_id, 'revision': '0'*64}, 'stale')
        call('tool unapproved source denied', {'operation': 'get', 'doc_id': 'workspace/PRIVATE.md', 'revision': '0'*64}, 'denied')
        if caller == 'gateway':
            call('tool incomplete search rejected', {'operation': 'search'}, 'invalid_request')
        else:
            call('tool authority override rejected', {'operation': 'search', 'query': 'Tom', 'audience': 'operator'}, 'invalid_request')
            call('tool oversized read rejected', {'operation': 'get', 'doc_id': docs[0].doc_id, 'revision': docs[0].revision, 'lines': 201}, 'invalid_request')
            call('tool disabled after enabled calls', {'operation': 'health'}, 'disabled', enabled=False)
        report['inputs_after'] = hashes()
        check('code authority and selected existing callers unchanged', report['inputs_before'] == report['inputs_after'])
        final = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, check=True).stdout
        check('existing API process not restarted', final == identity)
        report['passed'] = True
    except Exception as error:
        report['failure_type'] = type(error).__name__  # No exception text/token/source output.
    finally:
        receipt.write_text(json.dumps(report, indent=2)+'\n')
        receipt.chmod(0o600)
    return receipt, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--caller', choices=['stdio', 'plugin', 'gateway'], default='stdio')
    parser.add_argument('--gateway-session')
    parser.add_argument('--code-root', type=Path, default=ROOT)
    args = parser.parse_args()
    receipt, report = verify(args.state, args.output_root, args.caller, args.code_root.resolve(), args.gateway_session)
    print(json.dumps({'receipt': str(receipt), 'passed': report['passed'], 'checks': len(report['checks'])}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
