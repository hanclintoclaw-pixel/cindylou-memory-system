# U4 packet25 — host-owned invocation integration patch design

2026-11-04; Sol/medium. **DESIGN ONLY: no implementation, installation or execution.**
This is a concrete host-private, version-coupled proposal against packet24's bound
checkout, not a supported external acquisition API. All real reader lanes remain
unavailable. No authority, active module identity, build equivalence, containment or
production write-denial gate is cleared by this document.

## Boundary and default-off contract

Public extensions may register a provider using documented `openclaw/plugin-sdk/*`
exports only. They must not import `src/plugins/*`, private-local
`memory-host-search`, this proposed executor or a copied host module. No new public
RPC, operator CLI, HTTP endpoint, session-key lookup or legacy-root fallback is
proposed. Public provider registration does not grant acquisition of a session lease.
A future public contract requires upstream host ownership; absent it, external
private acquisition returns `unavailable/unsupported_host_boundary` before inputs.

Proposed host-private files/functions below are **new names**, not existing APIs.
Keep the feature compile-time/default-off plus per-invocation explicit opt-in, with
no config/routing change in this packet. Disabled means no provider open, IPC,
worker allocation, private source resolution or identity scan. No automatic retry
through another provider kind or lower containment tier.

## File/function hook plan

Paths are relative to the installed host checkout. Five current hook excerpts are
bound privately; packet24 retains the broader 57 selected bindings. These locations
are planning anchors, not a claim of exhaustive integration or transitive review.

- `src/agents/embedded-agent-runner/run/attempt-memory-audience.ts`, existing
  `resolveEmbeddedAttemptMemoryAudience`: caller of this resolver, inside actual
  admitted attempt lifetime, supplies its returned audience and release custody to
  proposed `createInvocationMemoryExecutor`. Never reconstruct `admission.entry`,
  lineage or caller-current callback from IPC. Locate and review that actual caller
  and its finally/abort ownership before implementing; this packet does not assert
  an exact uninspected call-site patch. Supplied/delegated audiences retain existing
  owner custody: executor borrows and never releases another owner's lease.
- New `src/plugins/memory-invocation-executor.ts`: host-only closure retaining the
  exact `MemoryCallerContext`, audience, invocation/session incarnation, admission
  lifetime, generation leases and abort linkage. `createInvocationMemoryExecutor`,
  `dispatchInvocationRead`, `revokeInvocationExecutor`, `settleInvocationExecutor`.
  Acquisition uses the host's existing selected-provider path in `memory-runtime.ts`,
  not a plugin import. Native versus legacy is captured, never relabelled.
- `src/plugins/memory-provider-adapter.ts`, existing `bindMemoryProvider`: retain its
  caller/plugin pre/post-await checks and reference/capability validation. Add a
  host-private dispatch fence, not an SDK signature change. Its outer `invoke`
  cannot authorize or roll back provider-internal writes; see effect gate below.
- New `src/plugins/memory-invocation-protocol.ts`: closed, versioned message parser,
  bound MessagePort routing, bounded sizes and one-shot request accounting. New
  `memory-invocation-identity.ts`: host-minted identity receipt and strict validator.
  Neither is exported through plugin SDK or serialized as a session grant.
- `src/plugins/loader-runtime-candidate.ts` and
  `plugin-runtime-artifact-binding.ts`, existing `bindPluginRuntimeArtifactSelection`,
  `hasCompletedPluginRuntimeRegistration`, `getPluginRuntimeEntrySource`: capture
  actual selected artifact and completed loaded-record instance at registration;
  finalize receipt only after actual load/registration succeeds. Hook the real
  loader owner, not discovery/status output. Retire receipts with the plugin instance.
- `src/infra/worker-task-host.ts`, existing `createWorkerTaskHost.createWorker`:
  bind resolved URL/options/owner before either `createCpuTrackedWorker` or
  `createRetainedNativeWorker`; require readiness acknowledgement with the actual
  loaded closure before dispatch. `runtime-worker-url.ts` remains authoritative for
  URL/execArgv selection; do not hard-code canonical dist wrapper names.
- `src/infra/worker-native-lifecycle.ts`, existing
  `captureRetainedNativeWorkerSource`: capture runtime generation, supervisor and
  broker URLs; join handles, resource close and retiring broker receipts on teardown.
  New `src/plugins/memory-invocation-*.test.ts` and scratch fixture modules specify
  deterministic controls below. No test file is implemented by packet25.

## Non-wire custody and wire schemas

Host custody `ExecutorRecord` (never serializable): frozen unique object identity;
exact admitted context and host-minted audience; actual agent/invocation and session
incarnations/lineage leases; caller-current callback; borrowed/owned release role;
selected loaded plugin instance/provider handle; runtime generation/identity receipt;
channel endpoint object; epoch; next sequence; bounded in-flight map; abort controller;
state; pending worker/thread/native resources; release-once latch. No raw audience,
session entry, store path, lease callback or authority object goes over IPC.

Wire v1 is a closed discriminated union; reject unknown fields/versions, oversized
frames and wrong types before dispatch. IDs are opaque correlations, not authority.
No caller-selectable agent/session/audience/provider/root/worker URL/command/env.

- `ReadRequest = {v:1, type:'read', channelNonce, invocationNonce, requestId,
  seq, epoch, identityReceiptId, op:'search'|'get', args}`. Search args have bounded
  query/limit and an allowed source subset; get args have provider-bound reference,
  revision and bounded range/maxChars. Limits are host-owned constants, not wire
  overrides. References are checked against this invocation/provider/generation;
  possession is not access. No arbitrary path or executable operation.
- `ReadResult = {v:1, type:'result', requestId, seq, epoch, identityReceiptId,
  status:'ok'|'denied'|'stale'|'unavailable'|'cancelled', payload?}`. Only `ok` has
  a schema-validated bounded page/passage, citations and coverage/status metadata.
  Scan/validate the whole serialized envelope, including citations/excerpts, before
  egress. No raw exception, path, hidden count, private ID or partial payload on error.
- `Cancel = {v:1,type:'cancel',requestId,seq,epoch}` cancels only its mapped request;
  duplicates are idempotent. `Close = {v:1,type:'close',epoch}` stops admission.
  Host-initiated invalidation stops egress immediately without waiting for peer ACK.
  A close acknowledgement is never a settlement proof.

Bind the channel to the retained admitted endpoint at creation, not by a user-supplied
nonce. Never accept a handle on another port/process/invocation even if bytes match.
Do not pass the authority port to provider-controlled descendants. Bound nonce/epoch
and strictly increasing sequence plus a consumed-request ledger reject replay and
out-of-order duplicates; no cached result survives revocation. Cap in-flight requests,
message bytes, result bytes, wall time and resource lifetime; unknown limits deny.

## Lifecycle, currency and race protocol

State machine: `disabled -> unavailable`, or `admitting -> active -> revoking ->
settling -> closed`; failed admission enters settling if it acquired resources.
Never reactivate an executor/epoch; a fresh invocation gets a fresh record/channel.
All transitions and request admission use one host-owned serialized turnstile.

1. Under admission custody, check actual context/audience, caller, session lineage
   and generations; capture loaded selected provider instance and registration.
   Validate identity/provenance/containment capabilities before opening a provider.
   Missing boundary/proof returns unavailable; no legacy/private-root substitute.
2. Create restricted channel and request ledger; retain exact leases. On dispatch,
   enter turnstile, require active state, endpoint/nonce/epoch/sequence/request match,
   current caller/audience/lineage, current plugin/worker generation and identity.
   Revalidate reference/revision and request capabilities, then acquire per-read
   generation preparation/lease using host-owned current-facts mechanisms.
3. Recheck after every awaited preparation/open. Bind a cancellation epoch to the
   operation. At each provider/worker boundary and immediately before every effect,
   require host currency and identity; post-await outer checks alone are insufficient.
4. Buffer the result privately. After provider completion, wait for this request's
   subordinate work/resources to settle; verify source/generation receipts, full
   output schema/policy/range and fresh caller/plugin/worker currency. Re-enter the
   same turnstile for final current check and transport enqueue. Revocation linearized
   first suppresses output; enqueue first is a disclosure committed while current.
   Bytes already delivered before revocation cannot be recalled. No streaming partial
   snippets; outbound transport must not independently retry buffered revoked results.
5. Any end/reset/reassign/parent revocation/plugin reload/identity drift/timeout/port
   loss sets revoking first, increments epoch, closes admission/egress and cancels
   queued/in-flight operations. Drain/drop results; don't wait for a cooperative peer
   to revoke. Release provider handles via permitted cleanup after revocation.
6. Settle all owned resources, then verify final generations and protection receipts.
   Release owned generation/audience leases once in finally; borrowed custody returns
   to its original owner. Cleanup failures retain receipts and mark unavailable,
   never healthy success or silently abandoned tasks. No private payload in logs.

### The effect gate is a separate, currently missing prerequisite

A check followed by an arbitrary asynchronous provider write has a TOCTOU gap.
There is no claim that calling `assertCurrent()` just before an await closes it.
For a read-only lane, compatible kernel confinement must deny every production write
regardless of revocation; scratch writes additionally require authorized effect
ordering. A mediated effect must acquire a host-owned generation fence whose
publication/revocation and actual effect commit have a defined shared linearization
protocol, or be a synchronous host-owned commit inside that fence. A remote worker
ACK/token followed by its own later write is not such a protocol. Unknown adapters,
unmediated effects, long external operations and unclosed generations deny execution.
This packet does not establish that existing generation helpers supply an atomic
mutation fence; implementation must audit/prove that separately or stay unavailable.
Result rejection cannot undo metadata, schema, WAL, cache, recall or origin effects.

## Loader-bound identity receipt and validator design

Host-private `LoadedMemoryIdentityV1`: receipt ID and issuer/boot nonce; host runtime
instance and generation; selected memory slot owner/plugin ID and instance generation;
provider ID and adapter kind (`native-providerRuntime` or `legacy-runtime`); completed
registration token; selection mode/recovery/setup policy; `api.source` and actual
`runtimeSource`/runtime and setup roots; artifact selection inputs and resolved real
URLs; loader/runtime executable/version/digest and flags/preloads; module load graph
with actual selected source/emitted URLs, content digests and immutable-generation
custody; worker kind and resolved URL/execArgv; supervisor/broker/child generations;
reached shared chunks/native SQLite/vector/embedding/PDF dependency identities;
build provenance linking source revision, build inputs/toolchain and output closure;
containment profile/generation and settlement capability IDs. Unknown is explicit.
Store paths/receipts privately; output only opaque receipt IDs and safe reason codes.

Validator `validateLoadedMemoryIdentity(record, actualOwner, expectedPolicy)`:

1. Require receipt minted in this host's private object registry; a JSON receipt,
   matching digest or copied boot nonce is not evidence of load. Require current
   boot/invocation/plugin generations, selected slot equality and complete registration.
2. Compare actual loader-selected roots, mode/recovery and loaded module identities,
   not nearby source filenames, CLI launcher guesses or registry discovery metadata.
   Require immutable content addressed load custody or equivalent actual-load evidence;
   hashing mutable files after loading cannot identify bytes previously loaded.
3. Require exact allowed adapter kind/provider ID. Observed Memory Core's legacy
   registration cannot silently become native `providerRuntime`; native failure
   never retries legacy. Changed generation/roots/policy invalidates pending work.
4. Validate reached worker readiness against the parent-issued generation and resolved
   entry/options; reject self-asserted worker hashes without loader/OS custody. Include
   direct/transitive dynamic imports and native libraries or fail closure incomplete.
   Hash the actual runtime binary and loader/preloads as part of provenance.
5. Validate reviewed emitted closure or trusted reproducible/release build provenance;
   source HEAD plus matching static hashes alone is not semantic build equivalence.
   Selection/receipt evidence and reviewed behavior/provenance are separate gates.
6. Revalidate at dispatch, before effects, after settlement and before egress; drift
   revokes the executor and never refreshes it in place. No hash helper opens a reader.

Existing host APIs do not supply this complete receipt today. Static packet24/25
bindings constrain the design revision; they are not active loaded identity receipts.

## Worker containment and settlement

Ordinary `Worker` threads share the host process, filesystem credentials and native
libraries. A child-only Seatbelt policy cannot confine those threads without also
confining the host. A future isolated worker-host process must have enforced sandbox
policy before provider/native initialization and restricted IPC, while actual audience
custody stays in the admitting host. Provider contexts cannot simply be cloned into
it. Until a revocation-preserving mediated adapter exists, that lane is unavailable.

Retained native transport adds runtime-generation-owned supervisor, spawn broker,
worker handles, child processes, resource-close receipts and retiring broker promises.
Do not kill a shared broker/host to settle one invocation: require an exclusive scoped
owner or proven per-invocation resource partition; otherwise unavailable. Threads
require exit/terminate join plus owned async/native task/MessagePort/resource closure;
processes require exit/reap plus broker/supervisor and descendant resource closure.
Top-level promise completion, AbortSignal, process-group kill or empty child list alone
is not proof against detached descendants, shared native jobs or surviving descriptors.

Future containment must support the actual required fork/thread/loader behavior while
denying writes to shared/per-agent databases and sidecars, schema/admission/registry,
publication/source/chunk/vector/origin/recall/meta, temp/cache/log/lock/lease/quarantine
and host cursor surfaces. Explicitly account for preopened descriptors, hardlinks,
symlinks, rename/replace, native extension writes and escaped descendants. Packet23's
fixed fork-denial child cannot admit this stack; configured network denial is not a
network test. Any unsupported OS primitive/settlement edge denies before real opens.

## Exact future scratch controls — specifications, NOT executed

Use only generated scratch text, fake provider and fake admission/loader fixtures;
no real readers/providers, private sessions, production DBs or network. Event barriers
must force interleavings; no sleeps as race proof. Save initial/final scratch hashes,
size/mtime/mode/inode/directory entries, request trace, generation/identity receipts,
effect counters and settlement receipts. An assertion failure preserves its receipt.
Control IDs below are a fixed acceptance specification, not an observed pass count.

- C01 default-off: supplied tripwire args/provider/channel factories must remain
  untouched; expect unavailable and zero allocations/opens/effects/output bytes.
- C02 positive: fixture host mints current context and loader receipt; one search
  and revision/range-bound get returns synthetic `ALLOWED-ONE` with one citation;
  all subordinate resources joined, owned release exactly once, no protected write.
- C03 forged grant: plain JSON/copy/local test token/operator scope/session key/
  legacy-root each fails host mint; zero provider calls and no payload/IDs/counts.
- C04 cross-invocation: replay C02 bytes on a second port/session incarnation/agent;
  deny before open even with matching request/receipt IDs.
- C05 delegation: valid fixture child retains parent; parent revoke at dispatch
  barrier denies child; detached/unknown/malformed lineage denies; no widening.
- C06 stale references: other-provider/wrong generation/changed revision/range
  escape and public direct get to private marker deny without any marker in envelope.
- C07 protocol: unsupported version/unknown field/oversize/query-limit/type errors,
  replay sequence/ID and second result each deny or close; zero duplicate dispatch.
- C08 revoke during admission/open: barrier each awaited stage; reset/reassign/end
  before continuation produces no operation effects/output; close/release once.
- C09 revoke before effect: pause fake provider immediately before mediated effect;
  revoke, resume; scratch effect counter remains zero and no partial result escapes.
- C10 commit ordering: hold fake atomic fence, race revoke versus scratch commit;
  exactly one linearized ordering; revoke-first means zero commit. An adapter without
  a fence fails unavailable, not a probabilistic pass based on result rejection.
- C11 revoke after computation/before egress: buffered synthetic secret never reaches
  the port; no citations/error/cache/retry leaks; effect-denial is checked separately.
- C12 enqueue ordering: barrier final turnstile; revocation-first drops, enqueue-first
  records authorized disclosure before revoke; no send after stale final check.
- C13 identity: change selected slot/adapter/provider/generation/recovery/root or
  completed-registration bit one at a time; fail before open and no legacy fallback.
- C14 loaded bytes: mutate on-disk file after fixture load; post-load disk digest
  cannot validate the old module. Missing immutable custody stays unavailable.
- C15 provenance: unchanged source HEAD but changed emitted/shared/native/preload/
  runtime binary closure or missing build provenance fails identity validation.
- C16 worker URL: source/package-local/root-dist/recovery fixtures select different
  entries; receipt must equal actual resolved entry+execArgv, not canonical guess.
- C17 worker spoof: correct URL but wrong generation/readiness/loaded closure denies;
  unsigned/self-asserted hashes and unknown dynamic/native imports stay unavailable.
- C18 thread: synthetic tracked thread with delayed async/native fixture and open
  MessagePort must not settle on its top-level result; wait for explicit resource joins.
- C19 native: synthetic supervisor/broker/child fixture retains resource-close and
  retiring broker receipts; each delayed receipt prevents settlement. Shared owner
  without scoped partition fails unavailable rather than killing unrelated work.
- C20 deadline/disconnect: cancel during each stage, then force supported scoped
  termination; no egress, all exclusive tasks reaped/joined, no orphan port/timer/file.
- C21 settlement failure: child exit with failed resource close or unresolved detached
  fixture yields unavailable, retained failure and no success; release custody once.
- C22 filesystem controls: synthetic protected targets exercise overwrite/create/
  unlink/rename/replace/chmod/symlink/hardlink/sidecar/preopened-FD writes, plus fork/
  detached spawn escape attempts under the actual proposed containment. Expect kernel
  denial and unchanged full protection receipts; any unsupported operation blocks lane.
- C23 write-surface fixture: one sentinel per DB/sidecar/schema/registry/admission/
  publication/source/chunk/vector/origin/recall/meta/temp/cache/log/lock/lease/cursor
  class; benign read with positive scratch allowance succeeds while each forbidden
  effect is denied. Synthetic coverage is not production deny proof.
- C24 effect bypass: fake provider writes directly instead of using the fence; require
  kernel denial, not merely stale result rejection. No compatible sandbox => unavailable.
- C25 cancellation cleanup: borrowed parent lease never released by executor; owned
  lease exactly once across open failure, duplicate close, timeout and cleanup failure.
- C26 envelope leak: out-of-range first-line `SECRET-OUTSIDE`, hidden private marker
  in citation/excerpt/error and doc-ID-without-fact must not pass evidence checks.
- C27 source drift after work/settlement: change fixture generation before final
  check; return stale without payload, never retry under newly observed generation.
- C28 unsupported boundary: missing host acquisition, active dependency identity,
  atomic effect custody, containment or settlement proof each yields unavailable before
  reader input/open; no synthetic positive upgrades either real lane.

## Packet25 validations, preservation and stopping point

Only design/schema/control-matrix static checks, hash/size/mtime preservation,
selected production git/process/socket comparisons and scoped git diff checks run.
No control C01–C28, integration/unit/full Python/Node suite, real reader/provider,
private session/raw transcript, model/HTTP/tool/live probe, production DB open or
build is run. Document checks are not host integration tests. Early context displays
were truncated; decisive five source windows are revision-bound and untruncated;
no source-review credit. Private receipt helper imports only the Python standard
library, not a host/reader module.

Preserve nineteen private/provisional/unresolved cases in two origin groups; 301/301
source-read, 0 unread, 184 mixed/unresolved tasks, 1206 findings, 0 promoted, unique
claims null and 32 partial/mixed summaries. No retrieval, eligible passage, answer
quality, loss, public parity or latency claim. Preserve prior partial24 receipts,
failures, originals/imports/OCR/quarantine and selected production dirty/caller/
config/registry/two-sectionpilot/API identity/socket; hash observations are not a
globally frozen state. Parent exclusively owns HEARTBEAT/notifier: neither edited
nor attested unchanged. No install/import/rebuild/restart/deploy, rights expansion,
promotion, primary reader/routing/config/voice/destruction/U5 change. Historical
conditional 18–30 active hours is not a new ETA; broader gates remain unfinished.

Stop after this one design packet for independent parent review. Proposed next bounded
step, only after that review: code-only refinement of the real admitted call-site and
atomic effect/loader custody gaps against exact host version, or a scratch-only
prototype implementing the reviewed default-off contract if evidence supports it.
Neither is started or authorized as a chained action by this packet's completion.
