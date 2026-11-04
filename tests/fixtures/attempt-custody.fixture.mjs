/** Packet27 ONLY. Fake local objects, no host/provider/reader imports or IO.
 * Not exported by production. Opt-in per invocation; no environment activation.
 * Fake identities, resources and scratch counters are not real authority.
 */
export function createFixtureBarrier() {
  let reach, release;
  const reached = new Promise(resolve => { reach = resolve; });
  const released = new Promise(resolve => { release = resolve; });
  return Object.freeze({ reached, release, async wait() { reach(); await released; } });
}

export function createAttemptCustodyFixture({
  bundledIdentity = 'fixture-generation-A',
  registrationComplete = true,
  preparationFailure = false,
  providerFailure = false,
  cleanupFailure = false,
  controlsFailure = false,
  effectBarrier,
  settlementBarrier,
} = {}) {
  // The fake loader and fake provider are fixed here, not injectable host adapters.
  const contexts = new WeakMap();
  const events = [];
  const counters = { acquisitions: 0, providerOpens: 0, effects: 0,
    ownedReleases: 0, borrowedReleases: 0, settled: 0, pending: 0 };
  const loader = Object.freeze({ identity: bundledIdentity, registrationComplete });
  const unavailable = reason => ({ status: 'unavailable', reason });

  function mintContext({ borrowed = false } = {}) {
    const opaque = Object.freeze(Object.create(null));
    contexts.set(opaque, { borrowed, revoked: false, attempts: new Set() });
    return opaque;
  }
  function revoke(context) {
    const record = contexts.get(context);
    if (!record) return false;
    record.revoked = true;
    for (const attempt of record.attempts) attempt.revoke();
    return true;
  }
  function acquire(record) {
    counters.acquisitions++;
    events.push('acquire');
    const abort = new AbortController();
    const attempt = { active: true, revoke() {
      attempt.active = false;
      abort.abort();
    }, abort };
    record.attempts.add(attempt);
    return { attempt, owned: !record.borrowed, release() {
      if (record.borrowed) counters.borrowedReleases++;
      else counters.ownedReleases++;
      events.push('release');
    } };
  }
  // This synchronous turnstile participates in THIS scratch effect only.
  // No awaits, caller callbacks, arbitrary DB writes or real mutation owner here.
  function commitScratch(record, attempt) {
    if (record.revoked || !attempt.active || attempt.abort.signal.aborted) {
      events.push('effect-denied');
      return unavailable('fixture-revoked');
    }
    counters.effects++;
    events.push('effect');
    return { status: 'committed' };
  }
  async function openFakeProvider(record, attempt) {
    counters.providerOpens++;
    counters.pending++;
    events.push('provider-open');
    if (effectBarrier) await effectBarrier.wait();
    if (providerFailure) throw new Error('fixture-provider-failure');
    return commitScratch(record, attempt);
  }
  async function settleFakeResources() {
    events.push('settlement-start');
    if (settlementBarrier) await settlementBarrier.wait();
    counters.pending = 0;
    counters.settled++;
    events.push('settled');
    // Fault is AFTER fake settlement, never permission to release unsettled work.
    if (cleanupFailure) throw new Error('fixture-post-settlement-cleanup-failure');
  }
  async function run(context, { enabled = false } = {}) {
    if (enabled !== true) return unavailable('fixture-disabled');
    const record = contexts.get(context);
    if (!record || record.revoked) return unavailable('fixture-context');
    // Fail closed on the fixed fake loader's actual returned identity/register state.
    if (loader.identity !== 'fixture-generation-A') return unavailable('fixture-identity');
    if (loader.registrationComplete !== true) return unavailable('fixture-registration');
    const lease = acquire(record);
    try { // Immediate: no fallible preparation gap after acquisition.
      if (preparationFailure) throw new Error('fixture-preparation-failure');
      return await openFakeProvider(record, lease.attempt);
    } finally {
      // Revoke/abort FIRST, even on preparation failure. Outer context not closed.
      lease.attempt.revoke();
      events.push('revoke-abort');
      try {
        await settleFakeResources();
      } finally {
        try {
          events.push('controls-close');
          if (controlsFailure) throw new Error('fixture-controls-failure');
        } finally {
          record.attempts.delete(lease.attempt);
          if (lease.owned) lease.release();
        }
      }
    }
  }
  return Object.freeze({ mintContext, revoke, run,
    snapshot() { return { ...counters, events: [...events] }; } });
}
