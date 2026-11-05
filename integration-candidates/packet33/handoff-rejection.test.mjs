// Closed synthetic helpers only: no real authority or provider import.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
const load = f => readFileSync(new URL(f, import.meta.url), 'utf8');
const enable = (raw, name) => {
  const literal = `const ${name} = false;`;
  assert.equal(raw.split(literal).length, 2);
  return stripTypeScriptTypes(raw.replace(literal, `const ${name} = true;`));
};
async function fixture(mode) {
  const context = vm.createContext({});
  const admitted = Object.freeze({id: 1}), otherAdmitted = Object.freeze({id: 2});
  const audience = Object.freeze({agentId: 'synthetic-1'}), otherAudience = Object.freeze({agentId: 'synthetic-2'});
  const abort = new AbortController(), otherAbort = new AbortController();
  let active = true;
  const current = () => { if (!active || mode === 'stale-admitted') throw new Error('revoked'); };
  const caller = Object.freeze({authority: Object.freeze({kind: 'session', audience, sessionKey: 'synthetic-1', sandboxed: false}), signal: abort.signal, assertCurrent: current});
  const otherCaller = Object.freeze({authority: Object.freeze({kind: 'session', audience: otherAudience, sessionKey: 'synthetic-2', sandboxed: false}), signal: otherAbort.signal, assertCurrent: current});
  const binder = new vm.SourceTextModule(enable(load('./attempt-memory-binding.ts'), 'ATTEMPT_MEMORY_BINDING_ENABLED'), {context});
  const executor = new vm.SourceTextModule(enable(load('./memory-invocation-executor.ts'), 'INVOCATION_MEMORY_EXECUTOR_ENABLED'), {context});
  const link = spec => {
    if (spec.includes('attempt-memory-binding')) return binder;
    if (spec === './attempt-audience-custody.js') return new vm.SourceTextModule(stripTypeScriptTypes(load('../packet28/attempt-audience-custody.ts')), {context});
    const mocks = spec.includes('admitted-run-context') ? {
      resolveAdmittedRunActiveAssertion: (value, signal) => {assert.ok(value === admitted || value === otherAdmitted); return mode === 'unadmitted' ? undefined : () => {signal?.throwIfAborted(); current();};},
    } : {
      isHostMemoryAudience: value => mode !== 'unminted' && (value === audience || value === otherAudience),
      assertMemoryAudienceCurrent: value => {assert.ok(value === audience || value === otherAudience); if (mode === 'stale-audience') throw new Error('stale audience'); current();},
      assertMemoryCallerCurrent: value => {assert.ok(value === caller || value === otherCaller); value.assertCurrent(); value.signal.throwIfAborted();},
    };
    return new vm.SyntheticModule(Object.keys(mocks), function() {for (const [name,value] of Object.entries(mocks)) this.setExport(name,value);}, {context});
  };
  await binder.link(link); await binder.evaluate(); await executor.link(link); await executor.evaluate();
  const api = binder.namespace, exec = executor.namespace;
  const poison = new Proxy({}, {get() {throw new Error('request inspected');}, ownKeys() {throw new Error('request enumerated');}});
  const withFirst = (release, clear, operation) => api.withBoundAttemptAudienceCustody(release, clear, admitted, mode === 'missing-audience' ? undefined : audience, abort.signal, () => caller, operation);
  const create = capture => exec.createInvocationMemoryExecutor({optIn: true, capture: () => capture});
  const capture = binding => ({binding, admittedRunContext: admitted, callerContext: caller, signal: abort.signal});
  return {api, exec, admitted, otherAdmitted, audience, otherAudience, abort, otherAbort, caller, otherCaller, withFirst, create, capture, poison, revoke: () => {active = false;}};
}
for (const mode of ['unadmitted','unminted','missing-audience','stale-admitted','stale-audience','pre-aborted']) test(`handoff refuses ${mode} before operation and releases once`, async () => {
  const f = await fixture(mode); const events = [];
  if (mode === 'pre-aborted') f.abort.abort();
  await assert.rejects(() => f.withFirst(() => events.push('release'), () => events.push('clear'), () => {throw new Error('operation must not start');}), error => !error.message.includes('operation must not start'));
  assert.deepEqual(events, ['release','clear']);
});
test('two independently current attempt handles cannot be crossed or copied', async () => {
  const f = await fixture();
  await f.withFirst(() => {}, () => {}, async (_own, binding) => {
    assert.equal(f.create(f.capture(binding)).status, 'prepared');
    await f.api.withBoundAttemptAudienceCustody(() => {}, () => {}, f.otherAdmitted, f.otherAudience, f.otherAbort.signal, () => f.otherCaller, async (_own2, otherBinding) => {
      const other = {binding: otherBinding, admittedRunContext: f.otherAdmitted, callerContext: f.otherCaller, signal: f.otherAbort.signal};
      assert.equal(f.create(other).status, 'prepared');
      for (const capture of [{...other, binding}, {...f.capture(binding), binding: otherBinding}, {...f.capture(binding), binding: {...binding}}, {...f.capture(binding), callerContext: f.otherCaller}, {...f.capture(binding), admittedRunContext: f.otherAdmitted}]) assert.equal(f.create(capture).status, 'unavailable');
      assert.equal(f.exec.dispatchInvocationRead({...binding}, f.poison).status, 'denied');
    });
  });
});
test('expired handle cannot create executor and retained executor denies poison request before release', async () => {
  const f = await fixture(); let binding, executor; const events = [];
  const invalid = () => {assert.equal(f.create(f.capture(binding)).status, 'unavailable'); assert.equal(f.exec.dispatchInvocationRead(executor, f.poison).status, 'denied');};
  await assert.rejects(() => f.withFirst(() => {invalid(); events.push('release'); throw new Error('release fault');}, () => {invalid(); events.push('clear');}, (own, b) => {
    binding = b; executor = f.create(f.capture(b)).executor;
    assert.equal(f.exec.dispatchInvocationRead(executor, f.poison).status, 'unavailable');
    own({close: () => {invalid(); events.push('close'); throw new Error('close fault');}});
    throw new Error('setup fault');
  }), /release fault/);
  invalid(); assert.deepEqual(events, ['close','release','clear']);
});
test('attempt abort revokes prepared executor before any request access', async () => {
  const f = await fixture();
  await f.withFirst(() => {}, () => {}, async (_own, b) => {
    const e = f.create(f.capture(b)).executor; f.abort.abort();
    assert.equal(f.exec.dispatchInvocationRead(e, f.poison).status, 'denied');
    assert.equal(f.create(f.capture(b)).status, 'unavailable');
  });
});
