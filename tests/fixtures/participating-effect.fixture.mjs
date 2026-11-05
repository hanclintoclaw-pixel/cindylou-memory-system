/** Packet39: closed synthetic state machine only. No IO, imports, SQL, callbacks,
 * provider/host hooks or activation option. Fake owner reports are not authority.
 * Tests enable exactly the literal below inside an isolated VM module.
 */
const FIXTURE_POLICY_ENABLED = false;

export function createParticipatingEffectFixture(options) {
  if (!FIXTURE_POLICY_ENABLED) return unavailable('fixture-disabled');
  const config = options ?? {};
  if (config.runtimeIdentity !== 'fake-runtime-1' ||
      config.sourceEligible !== true || config.completeOwners !== true ||
      config.recoveryCertain !== true || config.instantaneousAbort === true) {
    return unavailable('fixture-prerequisites');
  }
  const opaque = () => Object.freeze(Object.create(null));
  const events = [];
  const attempts = new WeakMap(), operations = new WeakMap(), permits = new WeakMap();
  // Fixed complete cohort; no caller-provided/dynamic owner or sink selection.
  const owners = new Map(['plugin', 'session'].map(id => [id,
    { id, generation: 1, phase: 'live', holders: new Set() }]));
  const connection = opaque();
  const store = { generation: 1, active: config.alreadyActiveTransaction === true,
    permit: null, quarantine: false, opens: 0, commits: 0 };
  let sequence = 0, releases = 0, attemptReleases = 0;
  const event = (type, detail = {}) => events.push({ type, ...detail });
  function mintAttempt({ borrowed = false } = {}) {
    const handle = opaque();
    attempts.set(handle, { borrowed, closed: false, attemptAbort: false,
      laneAbort: false, generations: [...owners.values()].map(o => o.generation) });
    return handle;
  }
  function current(attempt) {
    const a = attempts.get(attempt);
    return a && !a.closed && !a.attemptAbort && !a.laneAbort &&
      [...owners.values()].every((o, i) =>
        o.phase === 'live' && o.generation === a.generations[i]);
  }
  function prepare(attempt, { sink = 'scratch', intent = 'fixed-write',
    nested = false } = {}) {
    if (!current(attempt)) return unavailable('attempt');
    if (sink !== 'scratch' || intent !== 'fixed-write') return unavailable('undeclared-effect');
    if (nested || store.active) return unavailable('outermost-required');
    if (store.quarantine) return unavailable('quarantined');
    const operation = opaque();
    // All binding identities are internal, immutable and specific to this operation.
    const binding = Object.freeze({ attempt, connection, intent: opaque(),
      transaction: opaque(), nonce: opaque(), storeGeneration: store.generation });
    operations.set(operation, { binding, admitted: false });
    return { status: 'prepared', operation, binding };
  }
  function effective(owner) {
    if (owner.phase === 'pending' && owner.holders.size === 0) {
      owner.phase = 'effective';
      owner.generation++;
      event('effective-revoke', { owner: owner.id, generation: owner.generation });
    }
  }
  function revoke(id) {
    const owner = owners.get(id);
    if (!owner) return unavailable('unknown-owner');
    if (owner.phase === 'live') {
      owner.phase = 'pending';
      event('pending-revoke', { owner: id });
    }
    effective(owner);
    return { status: owner.phase };
  }
  function reserve(operation) {
    const op = operations.get(operation);
    if (!op || op.admitted || !current(op.binding.attempt)) return unavailable('operation');
    // Check + BEGIN are one synchronous fake-owner action under exclusive connection
    // custody. No awaits, callbacks, reentrancy or lock upgrades are possible here.
    if (store.active) return unavailable('outermost-required');
    if (store.quarantine || store.permit) return unavailable('store-busy');
    const permit = opaque();
    const cohort = [...owners.values()].sort((a, b) => a.id.localeCompare(b.id));
    for (const owner of cohort) {
      owner.holders.add(permit);
      event('fence-acquired', { owner: owner.id });
    }
    const record = { id: ++sequence, binding: op.binding, cohort, phase: 'reserved',
      consumed: false, outcome: 'not-committed', resources: 'pending', cleanupFailure: false };
    permits.set(permit, record);
    op.admitted = true;
    store.permit = permit;
    store.active = true;
    store.opens++;
    event('begin', { id: record.id });
    return { status: 'reserved', permit };
  }
  function consume(permit, suppliedBinding) {
    const r = permits.get(permit);
    if (!r || r.phase !== 'reserved' || r.consumed || store.permit !== permit ||
        !store.active || suppliedBinding !== r.binding) return unavailable('permit');
    const b = r.binding;
    for (const key of ['attempt', 'connection', 'intent', 'transaction', 'nonce', 'storeGeneration']) {
      if (suppliedBinding[key] !== b[key]) return unavailable('binding');
    }
    if (b.storeGeneration !== store.generation) return unavailable('generation');
    r.consumed = true;
    r.phase = 'in-flight';
    event('consume', { id: r.id });
    return { status: 'consumed' };
  }
  function commit(permit) {
    const r = permits.get(permit);
    if (!r || !r.consumed || !['in-flight', 'unknown'].includes(r.phase) ||
        r.outcome === 'committed' || store.permit !== permit) return unavailable('permit');
    // C is here, not reserve/consume. Pending revoke drains this winning reservation.
    store.commits++;
    r.outcome = 'committed';
    // A delayed fake-native C may arrive after its settlement channel was lost.
    // Keep quarantine/unknown resources until a separate trusted settlement report.
    if (r.phase !== 'unknown') r.phase = 'committed';
    event('commit', { id: r.id });
    return { status: 'committed' };
  }
  function release(permit, r) {
    // Only reached on explicit fake-native settlement, never timeout/abort/result ACK.
    r.phase = 'settled';
    store.active = false;
    store.permit = null;
    store.quarantine = false;
    for (const owner of r.cohort) {
      owner.holders.delete(permit);
      event('fence-released', { owner: owner.id, id: r.id });
    }
    releases++;
    const a = attempts.get(r.binding.attempt);
    a.closed = true;
    if (!a.borrowed) attemptReleases++;
    event('settled', { id: r.id, outcome: r.outcome });
    for (const owner of r.cohort) effective(owner);
  }
  function settle(permit, { outcome, resourcesSettled = false, cleanupFailure = false } = {}) {
    const r = permits.get(permit);
    if (!r || r.phase === 'settled' || r.phase === 'unknown') return unavailable('settlement');
    if (!['committed', 'rolled-back', 'unknown'].includes(outcome)) return unavailable('outcome');
    if ((outcome === 'committed' && r.outcome !== 'committed') ||
        (outcome === 'rolled-back' && r.outcome === 'committed')) return unavailable('contradictory-outcome');
    r.cleanupFailure ||= cleanupFailure;
    if (outcome === 'unknown' || resourcesSettled !== true) {
      if (r.outcome !== 'committed') r.outcome = 'unknown';
      r.phase = 'unknown';
      r.resources = 'unknown';
      store.quarantine = true;
      event('quarantined', { id: r.id, outcome: r.outcome });
      return { status: 'unknown', outcome: r.outcome };
    }
    r.outcome = outcome;
    r.resources = 'settled';
    release(permit, r);
    return { status: 'settled', outcome, cleanupFailure: r.cleanupFailure };
  }
  function reconcile(permit, { outcome, resourcesSettled = false } = {}) {
    // Explicit synthetic native-owner report only; NOT a real recovery mechanism.
    const r = permits.get(permit);
    if (!r || r.phase !== 'unknown' || resourcesSettled !== true ||
        !['committed', 'rolled-back'].includes(outcome)) return unavailable('reconciliation');
    if (outcome === 'committed' && r.outcome !== 'committed') return unavailable('unobserved-commit');
    if (outcome === 'rolled-back' && r.outcome === 'committed') return unavailable('contradictory-outcome');
    r.outcome = outcome;
    r.resources = 'settled';
    release(permit, r);
    return { status: 'settled', outcome };
  }
  function abort(attempt, arm) {
    const a = attempts.get(attempt);
    if (!a || !['attempt', 'lane'].includes(arm)) return unavailable('abort');
    a[arm === 'attempt' ? 'attemptAbort' : 'laneAbort'] = true;
    event('abort', { arm });
    return { status: 'delivery-denied' };
  }
  function deliver(permit) {
    const r = permits.get(permit), a = r && attempts.get(r.binding.attempt);
    const valid = r && r.phase === 'settled' && r.resources === 'settled' &&
      r.outcome === 'committed' && !r.cleanupFailure && !a.attemptAbort && !a.laneAbort &&
      [...owners.values()].every((o, i) => o.phase === 'live' && o.generation === a.generations[i]);
    return valid ? { status: 'delivered' } : unavailable('delivery');
  }
  return Object.freeze({ mintAttempt, prepare, reserve, consume, commit, settle,
    reconcile, revoke, abort, deliver,
    snapshot() { return { store: { ...store, permit: Boolean(store.permit) }, releases,
      attemptReleases, borrowedReleases: 0,
      owners: [...owners.values()].map(o => ({ id: o.id, generation: o.generation,
        phase: o.phase, holders: o.holders.size })), events: events.map(e => ({ ...e })) }; } });
}

function unavailable(reason) { return { status: 'unavailable', reason }; }
