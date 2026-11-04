// Additional local boundary controls. Closed VM; no real authority/provider imports.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
const raw = readFileSync(new URL('./attempt-memory-binding.ts', import.meta.url), 'utf8');
assert.equal((raw.match(/const ATTEMPT_MEMORY_BINDING_ENABLED = false;/g) ?? []).length, 1);
const source = stripTypeScriptTypes(raw.replace('const ATTEMPT_MEMORY_BINDING_ENABLED = false;', 'const ATTEMPT_MEMORY_BINDING_ENABLED = true;'));
const helper = stripTypeScriptTypes(readFileSync(new URL('../packet28/attempt-audience-custody.ts', import.meta.url), 'utf8'));

async function fixture(mode) {
  const context = vm.createContext({});
  const module = new vm.SourceTextModule(source, { context });
  const admitted = Object.freeze({}); const audience = Object.freeze({});
  let active = true;
  await module.link(specifier => {
    if (specifier === './attempt-audience-custody.js') return new vm.SourceTextModule(helper, { context });
    const mocks = specifier.includes('admitted-run-context') ? {
      resolveAdmittedRunActiveAssertion: value => { assert.equal(value, admitted); return mode === 'unadmitted' ? undefined : () => { if (!active || mode === 'stale-admitted') throw new Error('stale admitted'); }; },
    } : {
      isHostMemoryAudience: value => value === audience && mode !== 'unminted',
      assertMemoryAudienceCurrent: value => { assert.equal(value, audience); if (!active || mode === 'stale-audience') throw new Error('stale audience'); },
    };
    return new vm.SyntheticModule(Object.keys(mocks), function () { for (const [k,v] of Object.entries(mocks)) this.setExport(k,v); }, { context });
  });
  await module.evaluate();
  return { api: module.namespace, admitted, audience, revoke: () => { active = false; } };
}
for (const mode of ['unadmitted', 'unminted', 'missing-audience', 'stale-admitted', 'stale-audience']) {
  test(`binding refuses ${mode} before operation and releases once`, async () => {
    const f = await fixture(mode); const events = [];
    await assert.rejects(() => f.api.withBoundAttemptAudienceCustody(
      () => events.push('release'), () => events.push('clear'), f.admitted, mode === 'missing-audience' ? undefined : f.audience,
      () => { throw new Error('operation must not start'); },
    ), e => !e.message.includes('operation must not start'));
    assert.deepEqual(events, ['release', 'clear']);
  });
}
test('synchronous operation throw invalidates before throwing cleanup', async () => {
  const f = await fixture(); let captured; const events = [];
  const invalid = () => assert.throws(() => f.api.assertAttemptMemoryBinding(captured, f.admitted, f.audience), /binding unavailable/);
  await assert.rejects(() => f.api.withBoundAttemptAudienceCustody(
    () => { invalid(); events.push('release'); throw new Error('release fault'); },
    () => { invalid(); events.push('clear'); }, f.admitted, f.audience,
    (own, binding) => { captured = binding; own({close: () => { invalid(); events.push('close'); throw new Error('close fault'); }}); throw new Error('setup fault'); },
  ), /release fault/);
  assert.deepEqual(events, ['close', 'release', 'clear']);
});
test('revocation permanently invalidates a handle', async () => {
  const f = await fixture(); let captured;
  await f.api.withBoundAttemptAudienceCustody(() => {}, () => {}, f.admitted, f.audience, async (_own, binding) => {
    captured = binding; f.revoke();
    assert.throws(() => f.api.assertAttemptMemoryBinding(binding, f.admitted, f.audience), /stale/);
    assert.throws(() => f.api.assertAttemptMemoryBinding(binding, f.admitted, f.audience), /binding unavailable/);
  });
  assert.throws(() => f.api.assertAttemptMemoryBinding(captured, f.admitted, f.audience), /binding unavailable/);
});
