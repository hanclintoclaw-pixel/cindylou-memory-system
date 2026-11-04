# U4 packet26 — actual custody feasibility

2026-11-04; `openai/gpt-6.1-sol`, thinking medium. Code-only investigation;
no patch, host import, reader execution, build or installation.
Host checkout HEAD: `4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`.
The private packet26 source-window receipt binds **actual file bytes**, size and
mtime for each cited contiguous interval; HEAD alone is not its revision proof.
Existing packet24's 57 static bindings are retained, not active-load evidence.

## Engineering result: three questions resolved, no execution gate cleared

- **CLOSED — unknown attempt call-site/custody location:** the actual resolver,
  admitted-run assertion, audience handoff and finally release are located below.
  A small host-owned fixture seam is implementable without inventing acquisition.
- **CLOSED — whether the generation lease is an atomic effect fence:** it is not
  that contract. It observes prepared/committed session facts and supplies currency
  checks. A separate lifecycle mutation owner serializes participating identities;
  neither authorizes arbitrary reader-worker effects.
- **CLOSED — where loaded identity can attach and why current digest is inadequate:**
  real module loader, instance binding and successful registration are located.
  Crucially, bundled shared loading and non-bundled captured loading differ;
  bundled identity mismatch is a warning, not a fail-closed execution fence.
- **OPEN — actual host executor/IPC integration, atomic effect mediation, active
  dependency/build provenance, compatible confinement and full settlement.** Both
  real lanes stay unavailable. These findings close design uncertainties, not
  retrieval quality, loss, latency or production cutover gates.

## 1. Actual admitted-attempt caller and release custody

`src/agents/embedded-agent-runner/run/run-attempt-dispatch.ts`,
`prepareAndDispatchEmbeddedRunAttempt`:

- Lines 263–280 obtain `resolveAdmittedRunActiveAssertion(admittedRunContext,
  attemptAbortController.signal)`, reject its absence and recheck after an await.
- Lines 363–374 call `resolveEmbeddedAttemptMemoryAudience` with the actual
  `runInput.sessionAdmission`, resolved session identity and that assertion.
  No authority is reconstructed from a key, caller-provided audience or IPC JSON.
- Lines 375–404 create attempt controls from the admitted context and abort signal,
  and pass the exact returned audience into the attempt parameters.
- Lines 691–703 await `withPreparedEmbeddedGatewayTools`/backend; promise-finally
  closes attempt controls, releases the audience and clears the abort controller.

`src/agents/embedded-agent-runner/run/attempt-memory-audience.ts`,
`resolveEmbeddedAttemptMemoryAudience`, lines 18–65, resolves ownership precisely:
an already supplied audience must be host-minted/session-matching and returns the
no-op retained release because its delegating owner retains leases (28–34).
Without admission or with non-native loaded provider kind it returns no audience
(40–42); a newly granted native resolution returns its own release (43–55).
Legacy turns therefore cannot be upgraded to native/private by a wrapper.

**Attainable host hook:** retain the existing exact context/audience/assertion,
borrow supplied audiences and own only newly returned releases. Enclose all new
post-resolution allocation/preparation in an immediate `try/finally`; revoke the
new scope, await owned scratch-resource settlement, close attempt controls and
release once through nested finalizers so one cleanup failure cannot skip others.
The current promise-finally begins only at 691, after synchronous preparation at
375 onward. Do not insert fallible new allocation there and assume it is covered.
This is an insertion constraint, not proof of an existing leak.

The attempt scope must not close the outer admitted run or another owner's lease.
This bounded packet establishes the local attempt handoff/release, **not** a full
proof of every outer admission owner or cancellation/retained-resource lifecycle.
The inspected sibling `src/agents/harness/session-preparation.ts:35–86` has its own
admit/host/dispose/error-close custody; it is not this attempt's authority source.

## 2. Currency observations versus an actual effect fence

`src/config/sessions/session-delivery-generation.ts`:

- `prepareSessionGenerationLease:75–140` retains active/revoked state; release
  unsubscribes observers. Identity mismatch revokes. No effect callback exists.
- Lines 155–215 observe matching committed row changes, invalidate unsupported
  facts and subscribe to the facts channel.
- Lines 320–397 implement prepared reads and synchronous current assertions,
  observe public notifications after fact installation and expose only
  `assertCurrent`, `prepareRead`, `release` through `prepareSessionGenerationFacts`.
- The lifecycle-active check is conditional on `delivery` (328–343);
  `prepareSessionGenerationFacts` does not export `assertDeliveryCurrent`.
  Substituting the delivery variant would still be a check, not a commit fence.

`src/sessions/session-row-changes.ts:77–136`, `sessionChanges.emitBatch`, stages
fact installation on transaction commit, refreshes projections, then defers public
notifications until post-commit. This is **post-commit observation**. It cannot
prevent a separately running worker from writing after an earlier current check.

There is a real owner-side serialization mechanism, not an absent generic lock:
`src/sessions/session-lifecycle-admission.ts:206–320`,
`runExclusiveSessionLifecycleMutation`, normalizes/sorts all target identities,
serializes mutation activation, maintains active mutation state, exposes ingress
closure to preparation, runs under lifecycle identity locks and includes finalize
before releasing the owner. `src/sessions/session-lifecycle-locks.ts:1–91`,
`createSessionIdentityLockRunner`, uses shared lifecycle/mutation queue maps and
retains locks through awaited callback completion (not an OS or DB-global lock).

**Attainable, narrow option:** a host-owned, synchronous synthetic commit and
revocation can share one fixture turnstile; revoke-first forbids that scratch effect.
A future real mediated commit must live in its actual mutation owner, acquire all
participating owner fences, revalidate current facts there and commit under that
owner's synchronous transaction/commit protocol. A lifecycle mutation operation
cannot simply wrap a whole read: it changes admission semantics and may conflict
with current work. No such host change or transaction is made here.

**Unsupported boundary:** neither an IPC ACK, a leased facts object nor a promise
checked before/after an await fences unmediated native/worker/cache/DB effects.
Only participating owners share those queues; other processes do not inherit them.
All known production write surfaces must remain kernel-denied for a read-only lane.
No claim that every reset/reassign/plugin generation writer participates in one
commit protocol; that is still an explicit implementation prerequisite.

## 3. Actual loader/load identity custody, including the branch split

`src/plugins/loader-runtime-candidate.ts:415–490` resolves the execution artifact,
binds selection to the actual record, boundary-opens the entry, closes that FD,
then loads by `safeSource` through `params.loadPluginModule` (or recovery instance).
The closed FD/path check is not immutable custody of bytes subsequently loaded.
Lines 578–640 create the actual API, register in registry/instance scope, set
`runtimeRegistrationComplete` only after the capability-enabled register succeeds
(614–617), and publish `registry.plugins.push(record)` (619); failure rolls back
plugin global side effects. A selection-only receipt must not mark success early.

`src/plugins/loader-module-runtime.ts:106–174`, `createPluginModuleLoader`, captures
cache/options, finds/creates the real `PluginInstance` for the record, binds its
loader and expected digest, then calls `instance.loadModule`. The instance method
at `src/plugins/plugin-instance.ts:478–495` executes the bound loader under its
own scope and wraps its exports. Hook this instance/record, not a discovery record.

The decisive branch in `src/plugins/plugin-instance-module-loader.ts:35–130`:

- **Bundled (37–65):** expected source digest is explicitly inapplicable; use host
  cached loader and `bindSharedPluginModuleLoader`. Recapture is avoided because
  native ESM jobs can outlive an inventory generation.
- **Non-bundled (77–103):** `capturePluginGenerationArtifact` captures an artifact;
  expected digest mismatch disposes/throws, binds captured cache root, records
  `instance.sourceDigest`, and registers async disposal/recovery custody. This is
  useful existing machinery, not an end-to-end reviewed dependency/native closure.
  Host linking at 111–113 is an explicit separate boundary.

`src/plugins/plugin-shared-module-loader.ts:1–106` supplies actual bundled
export-object custody: a WeakMap associates canonical exports/default identity
with root and first observed digest. But fingerprint errors merely warn (30–43),
and reuse with unavailable/different identity stores a reload warning (65–80)
then **returns the value**. Recovery retains the loader facts. Thus this is
observability/reload diagnosis, not a complete fail-closed load receipt.

`src/plugins/plugin-module-loader-cache.ts:276–308` may reuse cached exports or
choose native JS versus source transform; lazy imports use their creating cache
generation. `src/plugins/plugin-runtime-artifact-identity.ts:100–175` hashes opened
files with same-file checks, but expressly hashes **plugin-owned files only**,
leaving dependency stores as separate runtime owners (130–133). Its content digest
cannot prove the native/shared/worker graph or source-to-build provenance.

**Attainable host hook:** record actual record/instance/adapter and selected entry
when its bound loader returns, finalize only after successful runtime registration,
retain origin/load-mode/cache-generation identity and retire with the instance.
For captured artifacts, reuse their actual custody rather than hashing mutable
source afterward. For bundled native reuse, an unknown/mismatch warning must leave
the proposed strict lane unavailable; do not silently recapture shared ESM or
equate a plugin-owned fingerprint with all loaded dependencies. A complete receipt
requires host/runtime/worker/dependency owners and trusted build provenance.

**Fundamental supported-surface limit:** these are host-private internals. Public
extensions use only documented `openclaw/plugin-sdk/*`; provider registration does
not expose admitted-context acquisition, lifecycle locks or these loader objects.
No supported external wrapper can manufacture them by importing copied internals.
Host-owned integration is feasible; an external private reader remains unsupported.

## Minimal implementable NEXT scope — one scratch-only host seam

After independent parent review, one default-off **fixture-only** prototype may
implement the resolved local attempt custody seam (not an installed host patch):
exact opaque fixture admitted context, borrowed/owned release, abort/revoke-first,
settlement-before-release, immediate try/finally after acquisition and a synchronous
fixture effect turnstile. Use fake provider/loader only. Four bounded controls:
owned release exactly once on success/failure; borrowed release never invoked;
forced revoke-before-commit leaves effect count zero; fake bundled identity
warning/unknown or incomplete registration returns unavailable before provider open.
Force interleavings with event barriers, not sleeps. No IPC, real provider, native
worker, production DB, kernel claim or actual load/build receipt is in that scope.
These controls are proposed, not executed by packet26. If prototype work needs a
broader host owner/API change, stop and report the exact missing boundary instead.

## Evidence, validation and preservation

Private packet26 source windows have code-only route preflight, exact revision
bindings and contiguous ranges <=80 lines/6000 original characters; no source
window output was truncated. Initial broad context/metadata outputs were truncated;
path searches encountered absent guessed paths/glob expansion errors. Three range
preflight failures exceeded actual EOF and displayed no rejected window; corrected
exact ranges were read. No missing-code assumption was used as a finding.

Only data/hash/static documentation checks, selected git/process/socket observations
and scoped diff/commit checks run. No host/fixture/unit/full Python/Node suites,
reader/provider imports, private sessions/raw transcripts, HTTP/model/tool/live
probe, production DB open/build, paired answer, eligible passage, quality/loss,
public parity or service latency measurement. Static source bindings are not active
load proof; selected preservation observations are not a globally frozen state.

Retain nineteen private/provisional/unresolved cases in two origin groups; 301/301
source-read, 0 unread, 184 mixed tasks, 1206 findings, 0 promoted, unique claims null,
32 partial/mixed summaries. All prior receipts/failures/originals/import/OCR/
quarantine and selected production11dirty/caller/config/registry/two-sectionpilot/
API38899command/socket preserved, with authorized append-only RESUME exception.
Parent exclusively owns HEARTBEAT/notifier; neither edited nor attested unchanged.
No rebuild/restart/deploy/import/rights/promotion/primaryreader/routing/config/voice/
destruction/U5. Historical conditional18–30hours is not a new ETA. Stop packet26;
no chained prototype. All broader acceptance gates remain unfinished.
