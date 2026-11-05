import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('./fixtures/participating-effect.fixture.mjs', import.meta.url), 'utf8');
const config = { runtimeIdentity: 'fake-runtime-1', sourceEligible: true,
  completeOwners: true, recoveryCertain: true };
function replaceOnce(text, before, after) {
  assert.equal(text.split(before).length, 2, 'mutation must match exactly once');
  return text.replace(before, after);
}
async function load({ enabled = true, mutant } = {}) {
  let text = source;
  if (enabled) text = replaceOnce(text, 'const FIXTURE_POLICY_ENABLED = false;',
    'const FIXTURE_POLICY_ENABLED = true;');
  if (mutant === 'release-on-ack') text = replaceOnce(text, "event('consume', { id: r.id });",
    "for (const o of r.cohort) o.holders.delete(permit);\n    event('consume', { id: r.id });");
  if (mutant?.startsWith('skip-')) text = replaceOnce(text,
    'const cohort = [...owners.values()].sort((a, b) => a.id.localeCompare(b.id));',
    `const cohort = [...owners.values()].filter(o => o.id !== '${mutant.slice(5)}').sort((a, b) => a.id.localeCompare(b.id));`);
  if (mutant === 'nested-admission') text = replaceOnce(text,
    "if (nested || store.active) return unavailable('outermost-required');", '/* omitted outermost admission */');
  if (mutant === 'savepoint-early-release') text = replaceOnce(text,
    'store.commits++;', 'release(permit, r);\n    store.commits++;');
  if (mutant === 'ignore-lane') text = replaceOnce(text,
    '!r.cleanupFailure && !a.attemptAbort && !a.laneAbort &&',
    '!r.cleanupFailure && !a.attemptAbort &&');
  const module = new vm.SourceTextModule(text, { context: vm.createContext({}) });
  await module.link(() => { throw new Error('fixture imports forbidden'); });
  await module.evaluate();
  return { create: module.namespace.createParticipatingEffectFixture, text };
}
const { create } = await load();
const fixture = (extra = {}) => create({ ...config, ...extra });
const unavailable = value => assert.equal(value.status, 'unavailable');
function prepared(f, attempt = f.mintAttempt()) {
  const p = f.prepare(attempt);
  assert.equal(p.status, 'prepared');
  return { ...p, attempt };
}
function reserved(f, attempt) {
  const p = prepared(f, attempt), r = f.reserve(p.operation);
  assert.equal(r.status, 'reserved');
  return { ...p, ...r };
}
function consumed(f, attempt) {
  const r = reserved(f, attempt);
  assert.equal(f.consume(r.permit, r.binding).status, 'consumed');
  return r;
}
function settleCommit(f, r, extra = {}) {
  assert.equal(f.commit(r.permit).status, 'committed');
  return f.settle(r.permit, { outcome: 'committed', resourcesSettled: true, ...extra });
}
function assertCommitBeforeEffective(f) {
  const events = f.snapshot().events;
  const c = events.findIndex(e => e.type === 'commit');
  const revokes = events.map((e, i) => e.type === 'effective-revoke' ? i : -1).filter(i => i >= 0);
  assert.ok(c >= 0 && revokes.length > 0 && revokes.every(r => c < r), 'C_BEFORE_EFFECTIVE_R');
}
function drainControl(make = fixture, owner = 'plugin') {
  const f = make(), r = consumed(f);
  f.revoke(owner);
  f.commit(r.permit);
  f.settle(r.permit, { outcome: 'committed', resourcesSettled: true });
  assertCommitBeforeEffective(f);
  return f;
}
function laneControl(make = fixture) {
  const f = make(), r = consumed(f);
  f.abort(r.attempt, 'lane');
  settleCommit(f, r);
  assert.equal(f.deliver(r.permit).status, 'unavailable', 'LANE_CANCEL_DENIES_DELIVERY');
}

test('shipped policy refuses before reading poison configuration; no enable option', async () => {
  const { create: disabled } = await load({ enabled: false });
  const poison = new Proxy({}, { get() { throw new Error('configuration touched'); } });
  assert.equal(disabled(poison).reason, 'fixture-disabled');
  assert.equal(disabled({ ...config, enabled: true }).reason, 'fixture-disabled');
});

test('complete fixed prerequisites required before fake store construction', () => {
  for (const change of [{ runtimeIdentity: 'unknown' }, { sourceEligible: false },
    { completeOwners: false }, { recoveryCertain: false }, { instantaneousAbort: true }]) {
    assert.equal(fixture(change).reason, 'fixture-prerequisites');
  }
});

test('positive fresh outer transaction consumes once and delivers only after settlement', () => {
  const f = fixture(), r = consumed(f);
  unavailable(f.deliver(r.permit));
  assert.equal(f.commit(r.permit).status, 'committed');
  unavailable(f.deliver(r.permit));
  assert.equal(f.snapshot().releases, 0);
  f.settle(r.permit, { outcome: 'committed', resourcesSettled: true });
  assert.equal(f.deliver(r.permit).status, 'delivered');
  assert.equal(f.snapshot().store.commits, 1);
  assert.equal(f.snapshot().releases, 1);
  assert.equal(f.snapshot().attemptReleases, 1);
});

for (const owner of ['session', 'plugin']) {
  test(`${owner} effective first denies reservation before BEGIN`, () => {
    const f = fixture(), p = prepared(f);
    assert.equal(f.revoke(owner).status, 'effective');
    unavailable(f.reserve(p.operation));
    assert.equal(f.snapshot().store.opens, 0);
    assert.equal(f.snapshot().store.commits, 0);
  });
  test(`${owner} pending closes ingress but cannot become effective before winning commit settles`, () => {
    const f = fixture(), r = consumed(f);
    assert.equal(f.revoke(owner).status, 'pending');
    unavailable(f.prepare(f.mintAttempt()));
    assert.equal(f.snapshot().owners.find(o => o.id === owner).holders, 1);
    f.commit(r.permit);
    assert.equal(f.revoke(owner).status, 'pending');
    f.settle(r.permit, { outcome: 'committed', resourcesSettled: true });
    assertCommitBeforeEffective(f);
    assert.equal(f.revoke(owner).status, 'effective');
    unavailable(f.deliver(r.permit));
  });
}

for (const arm of ['attempt', 'lane']) {
  test(`${arm} abort after grant suppresses delivery but drains successful C honestly`, () => {
    const f = fixture(), r = reserved(f);
    f.abort(r.attempt, arm);
    unavailable(f.deliver(r.permit));
    assert.equal(f.snapshot().releases, 0);
    f.consume(r.permit, r.binding);
    settleCommit(f, r);
    assert.equal(f.snapshot().store.commits, 1);
    unavailable(f.deliver(r.permit));
  });
  test(`${arm} pre-aborted attempt rejects before store open`, () => {
    const f = fixture(), attempt = f.mintAttempt();
    f.abort(attempt, arm);
    unavailable(f.prepare(attempt));
    assert.equal(f.snapshot().store.opens, 0);
  });
}

test('all permit binding dimensions and copied/foreign handles reject before commit', () => {
  const f = fixture(), r = reserved(f), other = prepared(fixture());
  for (const key of ['attempt', 'connection', 'intent', 'transaction', 'nonce', 'storeGeneration']) {
    const changed = { ...r.binding, [key]: key === 'storeGeneration' ? 2 : other.binding[key] };
    unavailable(f.consume(r.permit, changed));
    assert.equal(f.snapshot().store.commits, 0);
  }
  unavailable(f.consume({ ...r.permit }, r.binding));
  unavailable(f.consume(JSON.parse(JSON.stringify(r.permit)), r.binding));
  unavailable(f.consume(r.permit, { ...r.binding }));
  unavailable(f.consume(r.permit, new Proxy({}, { get() { throw new Error('foreign binding touched'); } })));
  unavailable(fixture().consume(r.permit, r.binding));
  unavailable(f.commit(r.permit));
  assert.equal(f.consume(r.permit, r.binding).status, 'consumed');
  unavailable(f.consume(r.permit, r.binding));
  settleCommit(f, r);
  unavailable(f.commit(r.permit));
  unavailable(f.reserve(r.operation));
  unavailable(f.prepare(r.attempt));
});

test('committed then post-settlement cleanup failure preserves C and denies delivery', () => {
  const f = fixture(), r = consumed(f);
  const result = settleCommit(f, r, { cleanupFailure: true });
  assert.equal(result.outcome, 'committed');
  assert.equal(f.snapshot().store.commits, 1);
  assert.equal(f.snapshot().releases, 1);
  unavailable(f.deliver(r.permit));
  unavailable(f.settle(r.permit, { outcome: 'committed', resourcesSettled: true }));
  assert.equal(f.snapshot().releases, 1);
});

test('cleanup failure without resource settlement retains fences and known C', () => {
  const f = fixture(), r = consumed(f);
  f.commit(r.permit);
  const result = f.settle(r.permit, { outcome: 'committed', cleanupFailure: true });
  assert.equal(result.outcome, 'committed');
  assert.equal(f.snapshot().releases, 0);
  assert.equal(f.revoke('session').status, 'pending');
  assert.equal(f.reconcile(r.permit, { outcome: 'committed', resourcesSettled: true }).status, 'settled');
  assertCommitBeforeEffective(f);
  unavailable(f.deliver(r.permit));
});

test('lost ACK/death/timeout all modeled as unknown; no actual worker/crash/timer tested', () => {
    const f = fixture(), r = consumed(f);
    assert.equal(f.settle(r.permit, { outcome: 'unknown' }).status, 'unknown');
    assert.equal(f.revoke('plugin').status, 'pending');
    assert.equal(f.snapshot().store.quarantine, true);
    assert.equal(f.snapshot().releases, 0);
    unavailable(f.prepare(f.mintAttempt()));
    unavailable(f.settle(r.permit, { outcome: 'rolled-back', resourcesSettled: true }));
    unavailable(f.reconcile(r.permit, { outcome: 'rolled-back' }));
    unavailable(f.reconcile(r.permit, { outcome: 'committed', resourcesSettled: true }));
    f.reconcile(r.permit, { outcome: 'rolled-back', resourcesSettled: true });
    assert.equal(f.snapshot().store.commits, 0);
    assert.equal(f.snapshot().releases, 1);
    assert.equal(f.revoke('plugin').status, 'effective');
});

test('rollback after modeled DML has zero logical commits, no physical nonmutation claim', () => {
  const f = fixture(), r = consumed(f);
  assert.equal(f.settle(r.permit, { outcome: 'rolled-back', resourcesSettled: true }).outcome, 'rolled-back');
  assert.equal(f.snapshot().store.commits, 0);
  assert.equal(f.snapshot().releases, 1);
  unavailable(f.deliver(r.permit));
});

test('late fake-native C during unknown settlement stays fenced until reconciliation', () => {
  const f = fixture(), r = consumed(f);
  f.settle(r.permit, { outcome: 'unknown' });
  assert.equal(f.revoke('plugin').status, 'pending');
  assert.equal(f.revoke('session').status, 'pending');
  assert.equal(f.commit(r.permit).status, 'committed');
  assert.equal(f.snapshot().store.quarantine, true);
  assert.equal(f.snapshot().releases, 0);
  unavailable(f.commit(r.permit));
  unavailable(f.deliver(r.permit));
  f.reconcile(r.permit, { outcome: 'committed', resourcesSettled: true });
  assertCommitBeforeEffective(f);
  assert.equal(f.snapshot().store.commits, 1);
  assert.equal(f.snapshot().releases, 1);
  unavailable(f.deliver(r.permit));
});

test('failure before BEGIN leaves no owned resources or logical effects', () => {
  const f = fixture(), p = prepared(f);
  f.abort(p.attempt, 'attempt');
  unavailable(f.reserve(p.operation));
  assert.equal(f.snapshot().store.opens, 0);
  assert.equal(f.snapshot().releases, 0);
});

test('independent second store and undeclared sinks rejected; first C is not compensated', () => {
  const f = fixture(), r = consumed(f);
  settleCommit(f, r);
  for (const sink of ['second-store', 'cache', 'background', 'file']) {
    unavailable(f.prepare(f.mintAttempt(), { sink }));
  }
  assert.equal(f.snapshot().store.commits, 1);
  assert.equal(f.snapshot().store.opens, 1);
});

test('competing cohorts serialize without partial acquisition or lock upgrades', () => {
  const f = fixture(), one = prepared(f), two = prepared(f);
  const r = f.reserve(one.operation);
  unavailable(f.reserve(two.operation));
  assert.equal(f.snapshot().events.filter(e => e.type === 'fence-acquired').map(e => e.owner).join(','), 'plugin,session');
  assert.equal(f.snapshot().store.opens, 1);
  f.consume(r.permit, one.binding);
  settleCommit(f, r);
  const second = f.reserve(two.operation);
  assert.equal(second.status, 'reserved');
  f.settle(second.permit, { outcome: 'rolled-back', resourcesSettled: true });
  assert.equal(f.snapshot().releases, 2);
  assert.equal(f.snapshot().owners.every(o => o.holders === 0), true);
});

test('borrowed attempt is not released; own retained reservation releases exactly once', () => {
  const f = fixture(), r = consumed(f, f.mintAttempt({ borrowed: true }));
  settleCommit(f, r);
  assert.equal(f.snapshot().attemptReleases, 0);
  assert.equal(f.snapshot().borrowedReleases, 0);
  assert.equal(f.snapshot().releases, 1);
  unavailable(f.settle(r.permit, { outcome: 'committed', resourcesSettled: true }));
  assert.equal(f.snapshot().releases, 1);
});

test('nested and already-active transactions reject before BEGIN or permit access', () => {
  const f = fixture();
  assert.equal(f.prepare(f.mintAttempt(), { nested: true }).reason, 'outermost-required');
  assert.equal(f.snapshot().store.opens, 0);
  const active = fixture({ alreadyActiveTransaction: true });
  assert.equal(active.prepare(active.mintAttempt()).reason, 'outermost-required');
  assert.equal(active.snapshot().store.opens, 0);
});

test('prepared-then-competing-BEGIN is rechecked under exclusive owner custody', () => {
  const f = fixture(), a = prepared(f), b = prepared(f);
  f.reserve(b.operation);
  assert.equal(f.reserve(a.operation).reason, 'outermost-required');
  assert.equal(f.snapshot().store.opens, 1);
});

test('contradictory settlement cannot erase committed C or invent commit from ACK', () => {
  const f = fixture(), r = consumed(f);
  unavailable(f.settle(r.permit, { outcome: 'committed', resourcesSettled: true }));
  f.commit(r.permit);
  unavailable(f.settle(r.permit, { outcome: 'rolled-back', resourcesSettled: true }));
  assert.equal(f.snapshot().releases, 0);
  f.settle(r.permit, { outcome: 'unknown' });
  unavailable(f.reconcile(r.permit, { outcome: 'rolled-back', resourcesSettled: true }));
  assert.equal(f.snapshot().store.commits, 1);
  f.reconcile(r.permit, { outcome: 'committed', resourcesSettled: true });
  assert.equal(f.snapshot().releases, 1);
});

for (const mutant of ['release-on-ack', 'skip-plugin', 'skip-session', 'savepoint-early-release']) {
  test(`discrimination: ${mutant} fails effect ordering, not just result rejection`, async () => {
    const { create: broken } = await load({ mutant });
    const make = () => broken(config);
    const owner = mutant === 'skip-session' ? 'session' : 'plugin';
    assert.throws(() => drainControl(make, owner), error =>
      error.code === 'ERR_ASSERTION' && error.message.includes('C_BEFORE_EFFECTIVE_R'));
    drainControl(fixture, owner);
  });
}
test('discrimination: nested-admission omission fails the intended pre-BEGIN assertion', async () => {
  const { create: broken } = await load({ mutant: 'nested-admission' });
  const f = broken(config);
  assert.throws(() => assert.equal(f.prepare(f.mintAttempt(), { nested: true }).status,
    'unavailable', 'NESTED_BEFORE_BEGIN'), error => error.code === 'ERR_ASSERTION' &&
      error.message.includes('NESTED_BEFORE_BEGIN'));
});
test('discrimination: attempt-only delivery handoff fails lane-only abort control', async () => {
  const { create: broken } = await load({ mutant: 'ignore-lane' });
  assert.throws(() => laneControl(() => broken(config)), error =>
    error.code === 'ERR_ASSERTION' && error.message.includes('LANE_CANCEL_DENIES_DELIVERY'));
  laneControl();
});
