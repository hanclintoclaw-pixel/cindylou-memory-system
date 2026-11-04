import test from 'node:test';
import assert from 'node:assert/strict';
import { createAttemptCustodyFixture, createFixtureBarrier } from './fixtures/attempt-custody.fixture.mjs';

function ordered(events, ...labels) {
  for (let i = 1; i < labels.length; i++) {
    assert.ok(events.indexOf(labels[i - 1]) >= 0);
    assert.ok(events.indexOf(labels[i - 1]) < events.indexOf(labels[i]), events.join(','));
  }
}

test('default off, including truthy opt-ins, opens/acquires/effects nothing', async () => {
  const f = createAttemptCustodyFixture();
  const ctx = f.mintContext();
  for (const enabled of [undefined, false, 'true', 1]) {
    assert.equal((await f.run(ctx, { enabled })).reason, 'fixture-disabled');
  }
  assert.equal(f.snapshot().acquisitions, 0);
  assert.equal(f.snapshot().providerOpens, 0);
  assert.equal(f.snapshot().effects, 0);
});

for (const borrowed of [false, true]) {
  for (const fault of ['none', 'preparationFailure', 'providerFailure', 'cleanupFailure', 'controlsFailure']) {
    test(`${borrowed ? 'borrowed' : 'owned'} lease: ${fault}; settlement and exactly-owned release`, async () => {
      const f = createAttemptCustodyFixture(fault === 'none' ? {} : { [fault]: true });
      const ctx = f.mintContext({ borrowed });
      if (fault === 'none') assert.equal((await f.run(ctx, { enabled: true })).status, 'committed');
      else await assert.rejects(f.run(ctx, { enabled: true }), /fixture-.*failure/);
      const s = f.snapshot();
      assert.equal(s.acquisitions, 1);
      assert.equal(s.ownedReleases, borrowed ? 0 : 1);
      assert.equal(s.borrowedReleases, 0);
      assert.equal(s.settled, 1);
      assert.equal(s.pending, 0);
      assert.equal(s.providerOpens, fault === 'preparationFailure' ? 0 : 1);
      assert.equal(s.effects, ['none', 'cleanupFailure', 'controlsFailure'].includes(fault) ? 1 : 0);
      ordered(s.events, 'acquire', 'revoke-abort', 'settlement-start', 'settled', 'controls-close');
      if (!borrowed) ordered(s.events, 'settled', 'controls-close', 'release');
      else assert.ok(!s.events.includes('release'));
    });
  }
}

test('forced revoke after provider open but before synchronous commit prevents the scratch effect', async () => {
  const barrier = createFixtureBarrier();
  const f = createAttemptCustodyFixture({ effectBarrier: barrier });
  const ctx = f.mintContext();
  const running = f.run(ctx, { enabled: true });
  await barrier.reached;
  assert.equal(f.snapshot().providerOpens, 1);
  assert.equal(f.snapshot().effects, 0);
  assert.equal(f.revoke(ctx), true);
  barrier.release();
  assert.equal((await running).reason, 'fixture-revoked');
  assert.equal(f.snapshot().effects, 0);
  assert.equal(f.snapshot().ownedReleases, 1);
  assert.ok(f.snapshot().events.includes('effect-denied'));
});

test('owned release waits for explicit fake resource settlement acknowledgement', async () => {
  const barrier = createFixtureBarrier();
  const f = createAttemptCustodyFixture({ settlementBarrier: barrier });
  const running = f.run(f.mintContext(), { enabled: true });
  await barrier.reached;
  const pending = f.snapshot();
  assert.equal(pending.pending, 1);
  assert.equal(pending.ownedReleases, 0);
  assert.equal(pending.settled, 0);
  ordered(pending.events, 'effect', 'revoke-abort', 'settlement-start');
  barrier.release();
  await running;
  assert.equal(f.snapshot().pending, 0);
  assert.equal(f.snapshot().ownedReleases, 1);
});

for (const options of [
  { bundledIdentity: null }, { bundledIdentity: 'fixture-generation-B' },
  { bundledIdentity: 'unknown' }, { registrationComplete: false },
  { registrationComplete: 'true' },
]) {
  test(`fake loader fails closed before acquisition/open: ${JSON.stringify(options)}`, async () => {
    const f = createAttemptCustodyFixture(options);
    assert.equal((await f.run(f.mintContext(), { enabled: true })).status, 'unavailable');
    assert.equal(f.snapshot().acquisitions, 0);
    assert.equal(f.snapshot().providerOpens, 0);
    assert.equal(f.snapshot().effects, 0);
  });
}

test('foreign, serialized and invented contexts convey no fake grant', async () => {
  const f = createAttemptCustodyFixture();
  const other = createAttemptCustodyFixture();
  for (const ctx of [other.mintContext(), {}, JSON.parse(JSON.stringify(f.mintContext())),
    { sessionKey: 'fixture-key', sender: 'fixture-operator', audience: 'private' }]) {
    assert.equal((await f.run(ctx, { enabled: true })).reason, 'fixture-context');
  }
  assert.equal(f.snapshot().providerOpens, 0);
});

test('revoked context cannot reacquire; local cleanup does not close borrowed outer context', async () => {
  const f = createAttemptCustodyFixture();
  const ctx = f.mintContext({ borrowed: true });
  await f.run(ctx, { enabled: true });
  await f.run(ctx, { enabled: true });
  assert.equal(f.snapshot().effects, 2);
  assert.equal(f.snapshot().borrowedReleases, 0);
  f.revoke(ctx);
  assert.equal((await f.run(ctx, { enabled: true })).reason, 'fixture-context');
  assert.equal(f.snapshot().acquisitions, 2);
});

test('nested cleanup faults still release exactly once after provider failure', async () => {
  const f = createAttemptCustodyFixture({ providerFailure: true, cleanupFailure: true, controlsFailure: true });
  await assert.rejects(f.run(f.mintContext(), { enabled: true }), /fixture-controls-failure/);
  const s = f.snapshot();
  assert.equal(s.effects, 0);
  assert.equal(s.settled, 1);
  assert.equal(s.pending, 0);
  assert.equal(s.ownedReleases, 1);
  ordered(s.events, 'revoke-abort', 'settled', 'controls-close', 'release');
});
