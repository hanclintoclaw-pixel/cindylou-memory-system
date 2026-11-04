# U4 packet24 — host authority and emitted worker identity

2026-11-04; one bounded code-only feasibility audit, Sol/medium. **Real private/native
reader execution remains unavailable.** No readers/providers were imported or executed;
no private sessions/raw transcripts, production database opens, builds or live probes.
This report adds engineering evidence, not source review or claim clearance.

## Supported boundary and actual authority path

`O` denotes the installed checkout selected by the pnpm launcher. Paths below are
relative to that checkout. Selected source/emitted revisions are bound privately by
SHA-256, size and nanosecond mtime; code bindings were captured **after inspection**,
not before it and not retroactively at the interrupted packet's start.

- `docs/plugins/sdk-overview/memory-and-context.md:155` documents host selection and
  caller lifecycle. Public `MemoryPluginCapability.providerRuntime` lets a plugin
  **provide** search/get/health; `memory-host-search` remains **private-local**. Its
  exported acquisition function is not a supported external harness capability.
- `src/agents/embedded-agent-runner/run/attempt-memory-audience.ts:27` resolves an
  admitted native-provider attempt's audience and owns its release. A legacy owner
  derives no audience there. A supplied grant must already be host-minted and bound
  to this invocation session; copied turn metadata is not authority.
- `src/plugins/memory-audience.ts:34` uses process-local WeakSet/WeakMaps. The mint
  freezes the object and binds it to the invocation session and lineage records.
  Resolution checks exact session incarnations, recorded parent lifecycle, owner
  bit and durable root chat type. Missing/malformed/stale lineage denies access.
  Delegation binds a child incarnation (or explicitly detached row absence), retaining
  parent revocation. `release()` ends custody; stale/released records reject reuse.
- `src/config/sessions/session-delivery-generation.ts:395` supplies generation-fact
  leases with `assertCurrent`, `prepareRead` and release. Currency uses prepared
  facts and committed generation publications. This is code evidence, not a run
  proving revocation or exhaustive audit of its state/worker dependencies.
- `src/plugins/memory-runtime.ts:296` validates the host-minted audience and wraps
  `assertMemoryCallerCurrent` before/after provider open. The selected slot owner
  determines native versus legacy; native failure is not a legacy retry.
  `memory-provider-adapter.ts:22` checks caller and plugin lifetime around awaits,
  validates provider-scoped references/capabilities and permits cleanup after
  revocation. Providers must additionally check immediately before effects,
  including after internal awaits: outer result rejection cannot undo a write.
- `src/gateway/server-methods/memory-provider.ts:109` captures authenticated
  **operator** connection/admitted-run authority. RPC success cannot establish a
  session grant. Host/status authority also grants no private-session audience.

**Feasibility result:** the installed host has an in-process revocable audience
mechanism, but this packet establishes no supported external harness acquisition
or revocation-preserving IPC adapter. Serializing an audience loses its host mint;
a local test token, operator scope, session key or reference ID cannot replace it.
A host-owned invocation executor must keep authority in the host and mediate
requests/results under the retained lease. Such an executor is not implemented here.

## Selected provider and emitted artifact resolution

The pnpm launcher points to `openclaw.mjs` in this checkout; that launcher tries
`dist/entry.js`, then `dist/entry.mjs`. These are static launcher facts, **not**
observations of the active Gateway's loaded module map or build generation.

1. `src/plugins/loader-runtime-candidate.ts:390` resolves runtime versus setup,
   recovery and metadata modes, then binds the execution artifact before loading.
   `plugin-runtime-artifact-selection.ts` applies source/built/overlay policy,
   package-local output and root output; canonical `dist` can replace staging
   `dist-runtime`. Runtime memo state also matters. Do not select solely by a source
   checkout's HEAD or a convenient file with the same basename.
2. `plugin-runtime-artifact-binding.ts` retains selected runtime/setup roots,
   preference and completed registration on the loaded record.
   `registry-api.ts:96` distinguishes `api.source` from bound `runtimeSource`.
   `plugin-runtime-artifact-identity.ts:134` hashes bounded plugin-owned content,
   not dependency stores/VCS. This helper was read, **not invoked**; its digest would
   not alone cover host/shared chunks, native libraries or runtime authority.
3. The inspected `extensions/memory-core/index.ts:219` and emitted entry register
   `runtime: memoryRuntime`, not `providerRuntime`. Thus this inspected Memory Core
   registration follows the legacy adapter when neutrally opened. Calling its
   underlying native engine a native *providerRuntime* would conflate two meanings.
   No claim is made about the active loaded slot owner or arbitrary other plugins.
4. `extensions/memory-core/src/memory/manager-cpu-entrypoints.ts` declares search,
   index, publication, standing-intent and origin worker layouts. Its emitted root
   chunk uses its own `import.meta.url`. `src/infra/runtime-worker-url.ts:7` chooses
   explicit root/dist, nearest `/dist/` plus package-name switch, or source sibling.
   Node TypeScript preloads and Bun runtime arguments differ. Applying the observed
   root-dist descriptor/resolver statically selects the canonical wrappers below;
   package-local/source/recovery selection still requires actual owner evidence.

Observed canonical wrapper to direct emitted chunk mappings:

- `dist/extensions/memory-core/memory-search.worker.js` → `manager-search.worker-Ce4rCEdJ.mjs`
- `memory-index.worker.js` → `manager-index.worker-7vCCH9xC.mjs`
- `memory-publication.worker.js` → `manager-publication.worker-CNRnYhyN.mjs`
- `memory-entry-origins.worker.js` → `memory-entry-origins.worker-DDjf4kAD.mjs`
- `standing-intents.worker.js` → `standing-intents.worker-DWthwFnj.mjs`

KNN is separately selected by `manager-search-knn-entrypoint.ts`; its emitted child
imports SQLite/vector dependencies. Read-only KNN does not make its parent stack
read-only. The private manifest also binds the direct KNN imports and emitted
facade/provider chunk. These are **selected direct imports, not transitive closure
or source-to-build semantic equivalence**. Mere presence/hash/mtime is insufficient.

`worker-task-host.ts` can create ordinary Node Worker threads or retained native
transport depending on the owner. `worker-cpu.ts:68` constructs a Worker; retained
transport in `worker-native-lifecycle.ts` can bind a runtime generation and separate
supervisor/spawn broker. Therefore “all workers are forked children” is incorrect;
both threads and subprocess/native resource lifetimes must be covered. None was
started. Packet23's fixed fork-denying synthetic child cannot admit this stack.

## Required engineering gates — not cleared

- A host-owned acquisition point using the actual admitted context, exact agent,
  invocation, session lineage and caller lifetime; no reconstructed JSON grant.
  Any IPC must retain host custody and currency checks around each effect/result,
  reject end/reset/reassign/revoke races and deterministically release leases.
- A loader-bound identity receipt from the actual selected/registered owner:
  artifact policy, source/runtime root, recovery path, plugin generation, provider
  ID and adapter kind. Bind emitted code plus actual shared imports, runtime binary,
  loader/preloads, worker/child/supervisor/broker and reached native SQLite/vector,
  embedding/PDF dependencies. Require build/release provenance or reviewed emitted
  closure; source hashes are not build attestation.
- Fork/thread-compatible enforced confinement and complete descendant/resource
  settlement; production write denial across shared/per-agent DBs and sidecars,
  schema/admission/registry, temporary/cache/lock/log and host recall/origin surfaces.
  Recheck generations after settlement, not merely after a top-level promise.

**Next bounded packet:** prepare one default-off, code-only host integration patch
DESIGN for a host-owned invocation executor, revocation-preserving IPC contract and
loader-bound identity receipt/validator, with exact positive/negative scratch-control
specifications. Pin Sol/medium. Do not install/execute the patch or real readers;
report unavailable where the host lacks a supported boundary. Real execution is a
separate gate after authority, identity and containment proofs, not the next probe.

## Checks and retained limits

Private versioned `packet24-*-20261104.private.json` receipts record audit edges,
52 first-binding files plus five later code/SDK-document bindings, helper identity,
19 unchanged case/status assertions across two origin groups, preservation and
closure. First-binding preservation passes; final supplement comparison is separately
recorded. Reproducible stdlib-only hash helper is in the code tier, with exact path
and hash in the private supplement. No real-reader module imports are used by it.

348 prior artifact paths retain bytes except the authorized append-only RESUME;
its pre-existing Sol/medium directive is retained verbatim. The earlier partial
packet24 receipts remain originals, not a completed packet or retroactive baseline.
All 301 queued hashes, selected original/import/OCR/caller/config/registry/two-section
pilot, production HEAD/diff/11 dirty files and API PID38899 command/socket are checked.
These are selected hash/process/socket observations, not globally frozen state or a
new HTTP health probe. Historical 7957-file inventory is retained, not rerun.
HEARTBEAT/notifier are parent-owned: neither edited nor attested unchanged here.
Initial missing-path/glob lookups, diagnostic KeyError and truncated displays are
retained in the limitations receipt; decisive excerpts were targeted again.

No unit/full Python/Node suites, host grant/revoke integration controls, production
write-denial/containment or retrieval/eligible get/paired answer/quality/loss/public
parity/service latency measurements ran. All real lanes stay unavailable; eligible
passage not run, correctness unassessed, loss unknown. CP18/CP19 remain nineteen
private/provisional/unresolved units, not unique facts. 301/301 read, 0 unread,
184 mixed/unresolved tasks, 1206 findings, 0 promoted, unique claims null and all
32 partial/mixed summaries remain unchanged. Prior failures, receipts, originals,
quarantine and reference limits remain. No rebuild/restart/deploy/import, rights
expansion, promotion, primary reader/routing/config/voice/destruction/U5 changes.
All broader gates remain unfinished; historical conditional 18–30 active hours is
not a new ETA. Stop after packet24 for independent parent verification; no chaining.
