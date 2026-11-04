# U4 — bounded native persistence closure audit21

One private, code-only packet by Sol/high from audit20 checkpoint
`1210187e-d33f-4cf4-bc9b-5b708010e9da`, clean commit
`7a7e65251550b9529a74836a4633fbd1f13b788b`. No reader imports, reader execution,
database opens as a reader, HTTP/tool calls or live probes. **Not exhaustive
transitive closure and not read-only execution clearance.** This closes concrete
storage destinations behind previously unresolved wrappers, not the migration.

## Concrete host persistence

`O` = the source checkout `/Users/hanclaw/claw/openclaw`; `W` = this worktree.
Targeted inspected source revisions, sizes and mtimes are bound privately for45
files. Source HEAD remains pinned `4d94a9fac61f2e83331a09df18ad35cdfb1faf5c`.
Those source hashes do not independently prove the emitted `dist` files or dynamically
resolved packaged workers correspond to that source generation.

- **Dreaming recall/meta:** `O/extensions/memory-core/index.ts:212`–`:215`
  supplies `api.runtime.state.openKeyedStore`; `O/src/plugins/registry-runtime.ts:234`
  binds plugin identity/current-runtime checks to `createPluginStateKeyedStore`.
  `dreaming-state.ts:124`/`:148`/`:157` registers, deletes removed entries and writes
  individual metadata. `O/src/plugin-state/plugin-state-store.ts:213` routes register
  to the async worker client. Its captured host admission leads to
  `plugin-state.worker.ts:166` write transaction and `:189` register dispatch.
  The concrete destination is `plugin_state_entries` in the shared
  `<resolved state dir>/state/openclaw.sqlite`, not a workspace JSON file.
  Namespace retention/expiry can also delete rows; generic runtime writes are not
  restricted to the memory index. Host lifecycle and schema maintenance still need
  isolation, rather than relying on a search-only flag.
- **Host events:** `O/src/memory-host-sdk/events.ts:19` delegates to
  `event-store.ts:257`; sequenced journal and cursor use `memory-core` plugin state,
  `memory-host.events` and `memory-host.event-cursors`. Budgets are10000events and
  1000cursors. `plugin-state-store.journal.ts:102` allocates sequence, upserts both
  rows and enforces expiry/oldest eviction inside the worker-owned transaction.
  `plugin-state-store.retention.ts:58`–`:80` deletes oldest namespace entries.
  `resolveMemoryHostEventLogPath` names retired `memory/.dreams/events.jsonl` only
  for migration discovery; it is not the runtime append sink.
- **Origin lineage:** `O/extensions/memory-core/src/memory-entry-origins.ts:43`
  captures agent database identity and admits commands through
  `withOpenClawAgentDatabaseAsync` plus `openOpenClawAgentSqliteWorkerStore`.
  `memory-entry-origins.worker.ts:31` owns transaction/commit admission;
  `:63`–`:80` prepares missing origin schema and dispatches record/delete.
  `O/packages/memory-host-sdk/src/memory-entry-origins.ts:29` creates the STRICT
  `memory_entry_origins` table; `:90` inserts with conflict-ignore lineage identity.
  The default agent path is `<resolved state dir>/agents/<agent>/agent/openclaw-agent.sqlite`
  (`O/src/state/openclaw-agent-db.paths.ts:40`); explicit path overrides are possible.
  Reservations and rollback deletion are real write routes, not read metadata.

These are potential code paths. This audit does not infer that a historical search
actually caused any particular write. The separately surfaced host memory-search
tool's recall recording is not automatically executed by the neutral provider lease.

## Published database and selected descendants

- `W/unification/native_adapter.mjs:55` imports the pinned private-local facade
  from `dist`; `:60` opens the selected provider for `purpose: cli` with
  **operator.read over entirely public isolated inputs**. It is not a private/session
  adapter. `O/src/plugins/memory-runtime.ts:296` selects the configured owner and
  chooses native providerRuntime or legacy manager adaptation. Failures do not
  establish permission for a fallback to another authority.
- `O/extensions/memory-core/src/memory/manager.ts:155` opens the published DB;
  only status purpose selects readOnly. `manager-database-context.ts:98`–`:148`
  borrows the admitted agent connection and calls `admitSchema` for the non-readOnly
  case. `:285` resolves the publication worker and uses the agent SQLite worker store.
  `manager-publication.worker.ts:200` dispatches schema admission in a transaction.
  `O/packages/memory-host-sdk/src/host/memory-schema.ts:290`–`:355` runs schema/storage
  migration, recall schema, revision-row insertion, revision triggers, indexes and
  provenance setup. Manager acquisition is therefore not a no-write operation.
- Publication worker staging creates temporary SQLite tables/rows; source refresh,
  source/chunk/vector replacement/deletion, embedding-cache upsert/clear/prune and
  publication revision writes are additional sinks. `manager-source-index-kernel.ts:119`
  checks source hash before source deletion and clears chunks/vector entries;
  `manager-embedding-cache.ts:103` evicts up to100excess oldest cache rows per prune.
  `manager-sync-ops.ts:599` prunes after successful rebuild publication and `:613`
  removes released shadow database files. These are explicit mutation routes, not
  proof those mutations occur on every read.
- `manager-search-orchestration.ts:307`–`:322` may repair a **missing identity**
  through `syncAdmitted` even when normal onSearch sync is disabled. `:373` separately
  schedules dirty-background search sync. A search response is not evidence every
  accepted worker/background operation has settled.
- `manager-cpu-entrypoints.ts` resolves search/index/publication/origin workers in
  source, bundled or package layouts. `manager-cpu-worker-runtime.ts:40`/`:46`
  creates retrieval/index pools; `manager-search.worker.ts:114`/`:126` uses read-only
  agent opens on the inspected retrieval branch. The KNN supervisor spawns the runtime
  executable with a restricted child environment; `manager-search-knn.child.ts:51`
  opens readOnly plus `PRAGMA query_only=ON` and can load a native SQLite extension.
  This local read-only child edge is not whole-stack or native-library clearance.
- Shared plugin-state operations reach the host `sharedStateStore` process entrypoint
  (`O/src/infra/runtime-process-entrypoints.ts:33`) through the shared-state lifecycle
  owner. The write transaction and concrete tables above are traced; the generic
  owner/admission/schema/lease/worker graph is not exhaustively traced here.

## Remaining execution gates and design refinement

The nineteen existing CP18/CP19 questions, rubrics, source bindings and two shared
origin groups remain unchanged. All are private/provisional/unresolved/not promoted;
candidate identities are not unique facts. No private caller-bound adapter is proven.
Do not substitute public projection, legacy roots, operator authority or guessed
session grants to make the private comparison run.

The isolated design now explicitly requires production write denial for **both**
shared-state and per-agent DBs plus sidecars, worker temp storage, schema/admission/
registry state, locks, caches and logs. Bind source-to-compiled worker resolution and
provider/native dependency identities, isolate/prohibit host recall recording, and
check generations after descendants/background work settle. These are requirements,
not implemented guards or passing harness controls.

Still unclosed: emitted artifact/package-resolution equivalence; full host state/agent
admission, schema, WAL/lease/quarantine descendants; SQLite/native-extension libraries;
embedding provider transport/cache and generic worker runtime; third-party PDF behavior;
actual production-write-denial enforcement and host-minted private authority. No claim
all transitive write sinks have been enumerated. A further source audit alone must not
be reported as a successful benchmark, permission gate or runtime-isolation test.

After parent verification, the useful next engineering step is a separately bounded,
default-off isolation-supervisor/harness implementation with scratch-only controls and
unavailable private/native lanes until these dependencies are proven. That step is not
started here; real-reader execution is still a separate gate.

## Actual checks and preservation

- Data-only checks:19 retained case query hashes, nonempty rubrics/limits, unresolved
  status,2origin groups, unchanged prior design bytes and unchanged source-review totals.
- Code binding:45 targeted source paths; hashes/sizes/mtimes captured **after inspection,
  before packet/docs**, not retroactive start proof or complete-file semantic coverage.
- Start preservation:311prior artifact paths plus the existing301queued-source,
  original/import/OCR, selected source/caller/config/registry/two-section pilot,
  production HEAD/status/diff/11dirty fingerprints and API PID38899command/socket checks.
  Final preservation allows only append-only RESUME, with old bytes retained in git.
  Historical7957-file inventory receipts are retained, not claimed freshly rerun here.
- Git diff/staged checks and post-commit clean state; source binding compared again
  after packet/docs. No unit/full Python/Node rerun, negative harness controls, real
  retrieval gets, paired answers, correctness/loss/public-eligibility/latency measurements.

Early combined control/discovery output was truncated and some paths/globs failed;
decisive excerpts were read again in bounded targeted output. No corpus-reading credit
is claimed. The skill tool handler was unavailable; the installed filesystem skill
and validation reference were read. Prior receipts/failures/corrections/originals/
quarantine/reference limits remain. Parent alone owns HEARTBEAT/notifier; neither
edited nor attested unchanged by this worker. Old audit20 receipts are not repaired.
This checkpoint's completion manifest includes truthful unchanged source progress
solely for observer schema compatibility, not new source-review progress.

Totals remain301/301source-read,0unread,184mixed/unresolved tasks,1206findings,
0promoted,unique claims null; all32summaries remain partial/mixed. No imports/reimports,
rebuilds,restarts,deployment,rights expansion,promotion,primary reader/routing/config/
voice changes,destruction or U5. Original conditional18–30active-hour estimate remains
historical conditional only. Broader semantic/integration/capture/shadow/voice/live-table/
retirement gates are unfinished. Stop after this packet for parent verification.
