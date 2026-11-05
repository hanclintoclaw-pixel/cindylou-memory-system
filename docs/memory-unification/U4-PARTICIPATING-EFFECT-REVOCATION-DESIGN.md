# U4 — participating effect owners and revocation protocol (Packet37)

## Status and contract boundary

**Proposed design only. Nothing implemented, installed or exercised.** This packet
uses bounded code-only inspection at host source revision
`4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`; private evidence holds exact source
hashes and line windows. Static source binding is not loaded/runtime/build proof.
Packet36 accepted Packet35's composite cancellation handoff and local custody only.
It did not prove atomic native effects, global authority or whole-resource settlement.
Both literal default-off policies remain false; both real lanes remain unavailable.
No public enable switch is proposed.

Required narrow property: for a declared effect transaction E and every authority
owner A on which E depends, successful native commit C must be totally ordered
against A's **effective revocation R**. R-before-C forbids C; C-before-R may retain
the already committed effect, but a separately revoked result must not be delivered.
This is not rollback of earlier valid commits and not atomicity of an entire read
across independent stores. An abort request, an effective authority revocation and
confirmation that all native resources settled are different events.

If the requirement is instead “no native COMMIT after the instant AbortSignal
fires”, an already granted asynchronous worker commit cannot satisfy it with this
broker design. The lane stays unavailable unless the actual native owner can
establish that stronger ordering. Do not relabel drain-before-effective-revocation
as instantaneous cancellation. For the strict read-only comparison, even a valid
pre-revocation write is forbidden: exclusion/production write denial remains required.

## Concrete effect and revocation owners

Paths below are relative to the pinned host checkout. These are possible code paths,
not claims that a past search caused any particular mutation.

- **Agent publication/native connection:**
  `extensions/memory-core/src/memory/manager-publication.worker.ts:150–215`
  owns synchronous transactions; its `withCommit` calls `admit("commit")`, then
  the native commit callback. `:269–323` owns embedding-cache prune/clear/upsert;
  expected revision/tombstone checks are useful data guards, not authority fences.
  `:324–360` loads the vector extension and dispatches whole-index publication and
  source deletion. `manager-source-index-kernel.ts:119–147` clears source/index
  state under expected source hash. These effects belong to the actual admitted
  agent DB connection, not the attempt helper's JS object.
- **Agent origin/forget owner:**
  `extensions/memory-core/src/memory-entry-origins.worker.ts:24–85` borrows the
  agent executor connection, admits at transaction/commit and owns origin record,
  delete and forget/tombstone work. Missing origin schema is prepared in a separate
  transaction before the batch: rejecting the later batch does not undo that schema.
  `src/state/openclaw-agent-execution.worker.ts:321–359` adds file identity and
  restricted native admission. `openclaw-agent-execution-domain.ts:21–46`
  requires exactly one grant for the original native stage. Neither establishes
  that all authority mutation owners hold a commit-spanning reservation.
- **Shared-state worker:** `src/plugin-state/plugin-state.worker.ts:51–58,163–218`
  checks session-entry sources at transaction and commit stages and dispatches
  journal/register/delete/clear/expiry mutations inside the shared-state transaction.
  The commit-stage check occurs before returning from the transaction body; it is
  not proof that another authority owner cannot revoke before actual native COMMIT.
  `plugin-state-store.journal.ts:102–179` allocates sequence with cursor/journal
  writes and expiry/retention in that worker's transaction;
  `plugin-state-store.retention.ts:58–82` deletes namespace rows. The journal's
  local atomicity does not join this shared DB to the agent DB.
- **Open/bootstrap and follow-on work:**
  `manager-database-context.ts:98–150` admits schema when opening a writable
  published manager. `manager-search-orchestration.ts:307–325` can repair missing
  identity through sync, and `:365–387` tracks background search sync separately.
  `manager-sync-ops.ts:590–620` prunes cache after publication and removes released
  shadow files. A successful main publication/result cannot stand in for later
  cache or filesystem settlement. Temporary staging, schema/open maintenance,
  extension load, permissions, WAL/sidecars, cleanup and provider transport need
  exclusion or their own owner protocol; they cannot be erased by result rejection.
- **Session authority:**
  `src/config/sessions/session-delivery-generation.ts:90–137,315–350` retains
  current/revoked facts and checks exact generation/source. Lifecycle-active checks
  are conditional on delivery. `src/sessions/session-row-changes.ts:93–138`
  installs committed facts and defers public notification: this observes committed
  changes, not a pre-commit lock on another database. The actual lifecycle mutation
  owner `session-lifecycle-admission.ts:206–320` sorts identities, closes ingress,
  holds mutation ownership through awaited finalization and releases afterwards.
  These are plausible participation points; this packet does not prove every
  session reset/reassign/archive/access writer passes through them.
- **Plugin/runtime authority:** `src/plugins/registry-lifecycle.ts:277–350`
  removes registry epochs, closes admissions, quiesces instances and aborts
  controllers; `:401–414` tests exact active record and revokes its owner.
  `registry-runtime.ts:183–195,228–242` captures current lifecycle authority and
  supplies it to async keyed state. `plugin-state-store.ts:119–134` composes
  `withCurrent` callbacks. Current predicates are useful but not native commit
  ownership. Registry retirement, record revoke, instance quiesce and replacement
  epoch publication all require participation, not just the session observer.
  Attempt/lane cancellation and final expiry are additional authority inputs;
  Packet35's exact composite signal must remain intact, not be replaced by one arm.

## Why existing checks and grants are not the missing fence

`src/config/sessions/session-entry-current-admission.worker.ts:160–218`
reads native current facts, requests host admission and rechecks native facts after
that grant. The host decoder in `session-entry-current-admission.ts:68–108`
binds captured source and current predicates. This narrows the window but does not
hold the authority source until a foreign store's COMMIT.

`src/infra/sqlite-worker-operation-admission.ts:232–247` grants a waiting worker
with a SharedArrayBuffer CAS; `:480–507` unblocks native execution. `:129–135`
can refuse REQUESTED, but a decision already GRANTED records later refusal as a
cleanup failure. It does not retract that grant. `:439–478` separately publishes
post-commit facts/native settlement. In `src/infra/sqlite-transaction.ts:419–445`
the actual COMMIT follows the synchronous `withCommit` callback.

Discriminating race: worker reads current facts → host grants → host retires the
plugin or a foreign session writer commits revocation → worker executes native
COMMIT → response is rejected. Postchecks catch the stale response but cannot
undo its write. A same-process lock held only while granting has the same gap.
A lock held by the caller but ignored by registry/session/worker owners is not
exclusion. A transaction lock on the effect DB alone does not lock a foreign
authority DB. IPC receipt of “accepted” is not “native settled”; worker termination
or timeouts do not establish rollback, and a COMMIT may already have succeeded.

## Proposed host-owned protocol: one store, complete authority cohort

This is a specification, not an API already available to a public extension.
The smallest useful future seam is **one mediated scratch-store transaction**,
not an arbitrary effect callback and not a wrapper around the entire read.

1. **Declare before open.** Host selects an immutable attempt/owner cohort:
   exact admitted caller/audience/attempt pair and composite signal; session source
   identities and generations; plugin record/registry/instance epochs; selected
   effect store/connection/file identity; runtime/worker generation; bounded operation
   and effect-family digest. Opaque host custody, not caller JSON authority.
   Unknown owner, undeclared sink or unsupported lifetime returns unavailable before
   provider/store open. Open/bootstrap effects are not implicitly admitted.
2. **Prepare without external effects.** Compute bounded immutable intent in
   scratch storage only. The real owner must confine every preparatory native write;
   BEGIN/DML can already write a journal/WAL even if SQL later rolls back. No claim
   of physical non-mutation follows from transaction rollback. No provider calls,
   shared cache mutation or detached task is hidden in preparation.
3. **Acquire participating fences before the native transaction.** One host
   coordinator acquires the complete authority cohort in canonical order, then the
   effect-owner queue/connection. All participating revocations use that same order.
   Never have revocation hold a lifecycle lock while waiting on a worker whose
   commit needs that lock. Admission closes to new reservations as soon as revoke
   is pending. No lock upgrade, unknown dynamic cohort or nested unlisted store.
   Retry after a failed BEGIN releases/reacquires and revalidates the cohort.
4. **Retain a one-use commit reservation.** Under all fences, check exact current
   authority and physical store generation; bind operation nonce/intent/connection.
   Grant only this native transaction, not an arbitrary subsequent command. Retain
   ownership across IPC, all final native checks and COMMIT/ROLLBACK settlement.
   The actual publication/origin worker `withCommit` and shared-state transaction
   boundary must consume this reservation; ordinary admission ACK is insufficient.
   Every direct SQL/cache route must be mediated or denied. No callback reentrancy
   may release/revoke the fences while COMMIT is in flight.
5. **Linearize honestly.** C is successful native COMMIT, not issuance of the
   permit or delivery of its receipt. Effective R is serialized authority-generation
   publication after all older reservations have settled. R first makes the old
   generation permanently ineligible. If a reservation wins first, revocation closes
   new ingress immediately but its effective publication waits for that reservation:
   successful C is then before R; failure/rollback has no committed effect. Raw abort
   can suppress result delivery immediately, but is not evidence that a native
   transaction stopped. If policy requires R at the request instant, this option
   does not qualify and must remain unavailable.
6. **Settle before release.** Owner reports committed/rolled-back/unknown together
   with store generation, operation identity and native resource settlement. A result
   message alone is not settlement. Separate commit receipt from settlement to handle
   committed-then-cleanup-failed. Retain the exclusion while a commit outcome is
   unknown; close admission/quarantine that owner and reconcile through trusted
   native ownership before further effects. No timeout auto-release, blind retry,
   compensating delete or “aborted implies rolled back”. Release the exact owned
   reservation once; never release borrowed custody. Bound waiting by failing the
   lane closed, not by pretending uncertain resources settled.
7. **Revalidate delivery separately.** After all owned descendants and follow-on
   resources settle, check current authority/composite cancellation and suppress a
   revoked result. This does not roll back valid committed effects. New-generation
   requests need new grants; restoring old row values must not revive old epochs.

**Required upstream changes/blockers:** session lifecycle/committed-row mutation
owners and plugin registry/instance revoke/quiesce/publication owners must explicitly
join the coordinator and expose pending-close versus effective-revoked completion.
The existing synchronous `revokePluginRecord` cannot be treated as if it waited for
native settlement. A new host-owned async drain/finalize boundary or a truly native
common authority/effect owner is required; it cannot be manufactured by an external
adapter. The agent/shared worker admission owners must retain and authenticate the
reservation through native settlement and reject duplicate/cross-generation permits.
All foreign authority writers must participate or be excluded. On broker/worker crash,
old generations cannot be reused: recovery must fence or prove termination/settlement
of old native writers before reopening; source hashes and a restarted JS map do not
supply that proof. These prerequisites are not implemented or validated here.

## Independent stores: choose a smaller contract, not fictional rollback

- **Preferred for a read-only lane:** exclude effects and use a complete, source-
  eligible isolated partition with all production/shared DB, sidecar, cache and
  filesystem writes denied. Prove source set and complete containment separately;
  a snapshot is not private session authority. Missing containment/identity proof
  leaves the lane unavailable, never a lexical substitute labelled hybrid.
- **Single native owner option:** put the necessary authority epoch and the permitted
  effect in one actual transactional store/owner, with revocations writing that epoch
  through the same native serialization. This can provide atomic logical check/write
  for that store; it changes owner architecture and does not fence plugin/process
  authority or another store unless those owners join. Not selected as an implemented
  migration and not permission to copy private data into a public partition.
- **Mediated multi-store per-effect option:** serialize authority against each store's
  retained reservation, but report each commit independently. A second-store failure
  can leave the first valid effect committed. Cache pruning after publication and
  shared journal writes remain separate effects. Do not promise all-or-none read-wide
  effects or reverse them with compensating deletes.
- A real cross-store atomic unit would need a separately designed supported recovery/
  transaction coordinator and participating durable stores; ordinary locks, IPC ACKs,
  SQLite transactions on independent handles and postchecks are not that protocol.
  No distributed commit/rollback, ATTACH/WAL durability or all-host closure is claimed.

## Future discriminating controls — specifications only (0 executed)

Use deterministic barriers, no real readers, imports, workers, SQLite, provider or
network in the next fixture scope. A JS fixture can validate the state machine, not
native atomicity. Twelve bounded controls:

1. Revoke-effective first: stale reservation rejected; committed-effect count zero.
2. Commit reservation first: pause before commit; revoke enters pending-close, rejects
   new reservations and cannot announce effective R; settle C, then R; suppress result.
3. Abort while grant is in flight: immediate delivery denial, no false rollback claim;
   assert the stated drain semantics, and explicitly reject instantaneous-abort mode.
4. Reproduce old check/ACK race with a broken reservation release: mutant commits after
   effective R and must fail the invariant, unlike a mere result-current assertion.
5. Skip plugin fence while retaining session fence (and vice versa): forced revoke
   exposes each missing-owner mutant. Exact composite lane/attempt arms remain required.
6. Cross attempt/connection/intent/generation/nonce and duplicate permit consumption:
   reject before any commit callback; copying a serialized handle grants nothing.
7. Native commit reported then cleanup fails: retain committed outcome, deny delivery,
   no compensation/retry and release only on proven resource settlement.
8. Lost settlement/worker death/timeout: unknown outcome quarantines, keeps effective
   revocation completion pending and forbids reopening an old generation.
9. Failure before BEGIN and rollback after DML: zero logical commit, all owned cleanup
   joined; do not assert physical files unchanged or promote to production-read proof.
10. A second independent store rejects: first commit stays explicit, whole-read atomic
    success is refused. Attempt unlisted cache/background/file work: unavailable.
11. Competing sorted multi-identity cohorts, pending revocation and cleanup failure:
    no inversion/reentrant grant, ingress closed through settlement, exact-once owned
    release and no borrowed release.
12. Missing runtime/owner identity, incomplete source eligibility, recovery uncertainty
    or false default policy: unavailable before store/provider open; no enable option.

Next bounded implementation specification, **not started**: a default-off,
uninstalled synthetic participating-owner coordinator/state-machine fixture, one
fake store, two fake revocation owners, opaque single-use reservation, explicit
pending/effective revoke and unknown-settlement state; the twelve controls above.
No real host APIs or private reader become reachable. Native transaction integration
would require another authorized packet and upstream owner participation, not a
passing fixture. Independent protocol review should precede that implementation.

## Evidence and limits

Private evidence binds 22 source files in 37 bounded windows, four exact mutable
beforeimages and old closure-to-snapshot mappings; 267 Packet36 closure hash bindings
verified before mutation. This is bounded protocol reasoning, not exhaustive all-host
sink enumeration or new corpus source-review credit. Truncated context/discovery
output and absent guessed paths were not negative proof. Two rejected window-capture
preflights exceeded EOF; failures retained, exact terminal windows corrected.
Only source/data/hash/doc/git checks run; proposed controls executed **zero** times.
No prior suites, real reader/provider/session/native worker, production DB, live probe,
model/tool/network test, host build, install, restart, deploy or declaration retry.

Actual host authority, active loaded/dependency/build identity, compatible confinement,
whole-resource settlement, production-write denial and declaration acceptance remain
OPEN; atomic participating effects are specified, not proven. No quality/loss/parity/
latency claim, promotion, retirement, rebuild, U5, rights/routing/config/voice change or
ETA. Counts unchanged:301/301read,0unread,184mixed,1206observations,0promoted,
unique claims null,32partial summaries;19private cases/two groups remain unresolved.
All older evidence/manifests and Packet35 patch EOF whitespace defect retained.
HEARTBEAT/notifier are outside this packet; no fresh unchanged attestation.
Stop after this packet for parent verification.
