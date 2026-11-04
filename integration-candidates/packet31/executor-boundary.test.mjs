// Exact candidate source; closed VM imports. No real admission/provider is evaluated.
// Enabled-path controls replace ONE immutable policy literal inside the VM only.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';

let original = readFileSync(fileURLToPath(new URL('./memory-invocation-executor.ts', import.meta.url)), 'utf8');
// Deliberately broken VM-only variants must make the control suite fail.
const mutant = process.env.PACKET31_MUTANT;
if (mutant) {
  const replacements = {
    'omit-default-off': ['if (!INVOCATION_MEMORY_EXECUTOR_ENABLED) return { status: "unavailable", reason: "disabled" };', '/* deliberately removed disabled guard */'],
    'admit-copy': ['resolveAdmittedRunActiveAssertion(admittedRunContext, signal)', '(() => {})'],
  };
  assert.ok(Object.hasOwn(replacements, mutant), 'unknown mutant');
  const [before, after] = replacements[mutant];
  assert.equal(original.split(before).length, 2, 'one exact mutant change');
  original = original.replace(before, after);
}
const policy = 'const INVOCATION_MEMORY_EXECUTOR_ENABLED = false;';
assert.equal(original.split(policy).length, 2, 'exactly one VM policy substitution');

async function fixture(enabled = true) {
  let active = true;
  let audienceCurrent = true;
  const observed = [];
  const audiences = new WeakSet();
  const admissions = new WeakSet();
  const audience = Object.freeze({ kind: 'conversation', agentId: 'fixture-agent', sessionKey: 'fixture-session', sessionId: 'fixture-incarnation' });
  const admitted = Object.freeze({ operationalRunInstance: Object.freeze({ runId: 'fixture-run' }) });
  audiences.add(audience); admissions.add(admitted);
  const controller = new AbortController();
  const caller = {
    authority: { kind: 'session', audience, sessionKey: audience.sessionKey, sessionId: audience.sessionId, sandboxed: true },
    assertCurrent() { if (!active) throw new Error('PRIVATE-FAILURE'); },
    signal: controller.signal,
  };
  const context = vm.createContext({});
  const source = enabled ? original.replace(policy, 'const INVOCATION_MEMORY_EXECUTOR_ENABLED = true;') : original;
  const module = new vm.SourceTextModule(stripTypeScriptTypes(source), { context });
  const imports = {
    '../agents/admitted-run-context.js': {
      resolveAdmittedRunActiveAssertion(value, signal) {
        observed.push(['admitted', value, signal]);
        if (!admissions.has(value)) return undefined;
        return () => { if (!active || signal?.aborted) throw new Error('PRIVATE-FAILURE'); };
      },
    },
    './memory-audience.js': {
      isHostMemoryAudience: value => audiences.has(value),
      assertMemoryCallerCurrent(value) {
        observed.push(['caller', value]);
        value.assertCurrent(); value.signal?.throwIfAborted();
        assert.equal(value.authority.audience, audience);
        assert.equal(value.authority.sessionKey, audience.sessionKey);
        assert.equal(value.authority.sessionId, audience.sessionId);
        if (!audienceCurrent) throw new Error('PRIVATE-FAILURE');
      },
    },
  };
  await module.link(specifier => {
    assert.ok(Object.hasOwn(imports, specifier), `Forbidden import ${specifier}`);
    const values = imports[specifier];
    return new vm.SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value);
    }, { context });
  });
  await module.evaluate();
  const api = module.namespace;
  const create = (override = {}) => api.createInvocationMemoryExecutor({ optIn: true, capture: () => ({ admittedRunContext: admitted, callerContext: caller }), ...override });
  const tripwire = new Proxy({}, { get() { throw new Error('request accessed before prerequisites'); } });
  return { api, create, audience, admitted, caller, observed, controller, tripwire,
    revokeAdmission: () => { active = false; }, revokeAudience: () => { audienceCurrent = false; } };
}

test('shipped default-off policy touches no argument getter, capture or authority', async () => {
  const f = await fixture(false);
  const result = f.api.createInvocationMemoryExecutor(f.tripwire);
  assert.equal(result.reason, 'disabled'); assert.equal(f.observed.length, 0);
});
test('VM-enabled policy still requires explicit opt-in before capture', async () => {
  const f = await fixture();
  assert.equal(f.create({ optIn: false, capture() { throw new Error('must not capture'); } }).reason, 'opt_in_required');
  assert.equal(f.observed.length, 0);
});
test('exact original admission and caller objects retained, read remains unavailable before request access', async () => {
  const f = await fixture(); const r = f.create(); assert.equal(r.status, 'prepared');
  assert.equal(f.observed[0][1], f.admitted); assert.equal(f.observed[1][1], f.caller);
  assert.equal(f.api.dispatchInvocationRead(r.executor, f.tripwire).reason, 'integration_prerequisites_missing');
  assert.equal(f.observed.at(-1)[1], f.caller); assert.ok(Object.isFrozen(r.executor));
});
test('copied admission with identical IDs cannot substitute for host registry custody', async () => {
  const f = await fixture();
  assert.equal(f.create({ capture: () => ({ admittedRunContext: { ...f.admitted }, callerContext: f.caller }) }).reason, 'authority_unavailable');
});
test('copied audience with identical fields fails mint check', async () => {
  const f = await fixture(); f.caller.authority.audience = { ...f.audience };
  assert.equal(f.create().reason, 'authority_unavailable');
});
for (const authority of [{ kind: 'operator', scopes: ['operator.admin'] }, { kind: 'host', operation: 'recall' }]) {
  test(`${authority.kind} authority is not admitted session custody`, async () => {
    const f = await fixture(); f.caller.authority = authority;
    assert.equal(f.create().reason, 'authority_unavailable');
  });
}
for (const field of ['sessionKey', 'sessionId']) {
  test(`mismatched ${field} rejected at preparation`, async () => {
    const f = await fixture(); f.caller.authority[field] = 'other';
    assert.equal(f.create().reason, 'authority_unavailable');
  });
}
for (const fault of ['admission', 'audience', 'abort']) {
  test(`${fault} revocation suppresses use permanently without request access`, async () => {
    const f = await fixture(); const r = f.create();
    if (fault === 'admission') f.revokeAdmission();
    if (fault === 'audience') f.revokeAudience();
    if (fault === 'abort') f.controller.abort();
    assert.equal(f.api.dispatchInvocationRead(r.executor, f.tripwire).status, 'denied');
    assert.equal(f.api.dispatchInvocationRead(r.executor, f.tripwire).reason, 'invalid_executor');
  });
}
for (const change of [
  f => { f.caller.authority = { ...f.caller.authority }; },
  f => { f.caller.authority.kind = 'operator'; },
  f => { f.caller.authority.sessionKey = 'other'; },
  f => { f.caller.authority.sessionId = 'other'; },
  f => { f.caller.authority.sandboxed = false; },
  f => { f.caller.authority.audience = { ...f.audience }; },
  f => { f.caller.assertCurrent = () => {}; },
  f => { f.caller.signal = undefined; },
]) {
  test(`borrowed context mutation ${change.toString()} cannot refresh custody`, async () => {
    const f = await fixture(); const r = f.create(); change(f);
    assert.equal(f.api.dispatchInvocationRead(r.executor, f.tripwire).reason, 'authority_unavailable');
  });
}
test('copied, serialized and foreign module handles never acquire custody', async () => {
  const f = await fixture(); const g = await fixture(); const r = f.create();
  for (const value of [{ ...r.executor }, JSON.parse(JSON.stringify(r.executor)), g.create().executor]) {
    assert.equal(f.api.dispatchInvocationRead(value, f.tripwire).reason, 'invalid_executor');
  }
});
test('revoke and settle are idempotent, do not call borrowed release or caller checks', async () => {
  const f = await fixture(); const r = f.create(); const n = f.observed.length;
  f.api.revokeInvocationExecutor(r.executor); f.api.revokeInvocationExecutor(r.executor);
  f.api.settleInvocationExecutor(r.executor); f.api.settleInvocationExecutor(r.executor);
  assert.equal(f.observed.length, n);
  assert.equal(f.api.dispatchInvocationRead(r.executor, f.tripwire).reason, 'invalid_executor');
});
test('capture errors have no private exception payload', async () => {
  const f = await fixture(); const r = f.create({ capture() { throw new Error('PRIVATE-FAILURE'); } });
  assert.equal(r.reason, 'authority_unavailable'); assert.ok(!JSON.stringify(r).includes('PRIVATE'));
});
