# U4 — bounded reader-write audit20 and paired-evaluation design

Prepared by Sol/high from checkpoint `813c959e-0c4f-49f1-8070-140988c06893`,
clean `71262c04a0628ee62e23d2e4a49a8325e22a88c2`. One private preparation
packet only. No reader was imported, run or probed. **No execution clearance:** the
native transitive surface exceeds this bounded audit; unknown dependencies remain.
This is design, not an implemented harness or paired retrieval/answer result.

## Actual entrypoints and identified write edges

Line locations below refer to the content-bound revisions in the private code receipt.
`P` = `/Users/hanclaw/claw/projects/cindylou/memory-system`; `W` = this worktree;
`O` = `/Users/hanclaw/claw/openclaw`. Production dirty equipment code was inspected,
not assumed identical to the worktree. Native HEAD matches pinned `4d94a9f`.

- Legacy shell `/Users/hanclaw/.local/bin/cindylou:2` → `P/cindylou.py:15`
  loads `05_serving/memory_bridge.py`; search/get dispatch at `:35`/`:52`.
  Legacy HTTP `P/05_serving/memory_api_server.py:18` loads the same module;
  GET document `:43`, POST search `:65`. The wrapper at
  `W/scripts/memory_api_server.py:5` uses runpy, not a different backend.
- Legacy campaign search: `P/05_serving/memory_bridge.py:58`/`:96` root walker →
  `:151` keyword filesystem reads → `:233` semantic alias. Get `:825` reads text,
  optionally basename-falls back across roots, then head-caps it; no revision-bound
  passage contract. No explicit persistent writes in these campaign functions.
  Config `P/config/pipeline_paths.py:24` reads `.env` and mutates process environment;
  `:51` resolves paths. Import bytecode remains a possible interpreter write, so any
  future isolated child must prohibit bytecode and `.env`/root fallthrough explicitly.
- Adjacent legacy **mutation routes**, not invoked by search/get:
  `memory_bridge.py:862` appends facts and audit JSONL; `:893` entity queue;
  `:909` opens log and launches service; `:917` pkill/restart; `:942` rebuild launches
  three generators. Generator sinks: `P/03_organization/build_campaign_kb.py:22`
  import-time mkdir, `:368`/`:468` Markdown and `:481` JSON;
  `build_entity_manifest.py:61`/`:71` manifest replacement;
  `build_campaign_intro_timeline.py:297`/`:298` generated Markdown.
  These routes are not evidence historical search calls used them.
- Voice caller source `/Users/hanclaw/claw/projects/discord_voice_patch/voice_chat.py:2879`
  spawns legacy CLI search; `:3193` and `:3330` spawn get; `:3105` spawns the equipment
  CLI. No voice behavior changed or voice-wide transitive audit claimed.
- Equipment `P/scripts/equip_query.py:321`/`:451` opens SQLite with default writable
  connect, though inspected lookup SQL selects rows. `:196` corroborate → `:168`
  PDF extraction updates request cache; CLI `:526` saves it via `:157` mkdir/temp
  write/replace of `pdf_page_text.json`. SQLite sidecars and Python/PDF dependency
  behavior require isolation; a SELECT does not certify a whole process read-only.
- Shared `W/unification/service.py:33` dispatches explicit lexical/native/specialist/
  capture domains. Registry/policy reads (`registry.py:13`, `policy.py:177`) open
  approved files read-only and check revisions; lexical/get have no explicit persistent
  sink. `W/unification/specialists.py:60` clones equipment function globals, replaces
  saver with refusal and SQLite with `:55` ro+immutable/query_only, refuses nonempty
  WAL, and uses request-only PDF cache at `:205`–`:212`. This is source inspection,
  not fresh execution or third-party dependency closure.
- Capture is a **read-triggered writer** when configured: `W/unification/capture.py:71`
  constructor → bootstrap locks/staging/inventory (`:90`) → recover (`:369`). Search
  `:458`–`:461` reconciles SQLite through `:333`, deleting/reinserting records/terms/
  receipts and updating timestamps. History `:483` → `_records_locked` at `:171`
  → inventory at `:228` can adopt crash-orphan records. Index open `:260` creates
  schema/chmods, can quarantine corrupt DB/sidecars by rename. Canonical atomic
  inventory/record writes at `:382` include temp/fsync/replace. Public canary does
  not configure captures; do not infer all MemoryService reads are nonmutating.
- Public canary CLI `W/unification/canary_cli.py:40` supplies registry+partition,
  public context, native client and real MemoryService hybrid search. API
  `canary_api.py:40` delegates to it; tool `canary_tool.py:125` exchanges HTTP with
  that API. Plugin `W/integrations/openclaw-memory-canary/index.mjs:48` spawns
  isolated Python, with host-selected `api.source` release resolution at `:94`.
  Network response/stdout writes are not corpus writes, but the delegated native
  provider has deeper state writes. No live API/tool invocation occurred here.
- Native `W/unification/native_client.py:119` subprocess → `native_adapter.mjs:41`
  openAdapter → Python generation-validator subprocess `:49`, then private-local
  SDK `:55`/`:60` with **operator.read on entirely public isolated inputs only**.
  `O/src/plugin-sdk/memory-host-search.ts:51` → runtime re-export →
  `O/src/plugins/memory-runtime.ts:296` selects provider owner; legacy adaptation
  `memory-provider-adapter.ts:148` acquires manager and `:226` searches it.
  `O/extensions/memory-core/src/runtime-provider.ts:21` forwards manager acquisition.
- Native manager `O/extensions/memory-core/src/memory/manager.ts:155` opens published
  DB, readOnly **only for status** (`:158`); `:293` attaches lifecycle sync triggers.
  `manager-search-orchestration.ts:257` gates ordinary onSearch sync, but `:307`–`:322`
  repairs missing identity via syncAdmitted; `:373` starts background sync.
  `manager-search-maintenance.ts:37` syncs detached manager; `manager-sync-ops.ts:554`
  writes metadata. `manager-db.ts:28` enumerates DB/WAL/SHM/journal and `:152`
  declares crash-shadow cleanup. Turning off onSearch alone is no read-only proof.
- Distinct host memory-search **tool** path, not automatically the neutral provider:
  `O/extensions/memory-core/src/tools.ts:477`–`:488` asynchronously records surfaced
  recall; `short-term-promotion-record.ts:353` reserves origin lineage, `:359` writes
  store, `:363` appends host event. `short-term-promotion-store.ts:51` delegates to
  dreaming keyed-store replace/meta writes; `dreaming-state.ts:124`/`:157` write,
  `:148` deletes removed entries. Do not label these as flat metadata files without
  tracing the host-selected keyed-store backend. Gateway operator authority capture
  `O/src/gateway/server-methods/memory-provider.ts:106` is not a session/public grant.
- Source-generation preparation itself writes: `W/unification/partition.py:14`
  materializes exact public sections and manifest; `scripts/memory_public_partition_prepare.py:35`
  writes isolated native config. Neither ran. Existing shadow reader hard-codes
  production roots/cache (`scripts/memory_unification_shadow_readers.py:20`/`:22`),
  operator-only legacy baseline `:77` and asymmetric public unified `:162`; it is
  not an isolated/private paired harness for the current candidate packet.

## Explicit audit boundary and blockers

The native owner is plugin-selectable. Deeper host keyed-store implementation,
origin/event persistence, database schema/retention/publication/worker/subprocess and
embedding-provider closure, plus third-party PDF internals, are **not fully traced**.
No claim every transitive write sink is enumerated; no inference about historical
writes from these potential paths. No live process/database was opened as a reader.
The next gate is code-only closure of those unknowns, not benchmark execution.

## Paired design, not implementation

Private `audit20-paired-design-20261103.private.json` binds nineteen existing candidate
identities, exact UTF-8 queries/hashes, unchanged answer rubrics/limits and source
passage revisions from CP18/CP19. Two shared originating extraction groups are not
nineteen independent facts. Equivalence/unique claims remain unassessed.

Future design requires same query, host-issued current/revocable context and source/
caller/code/config/registry/partition generation on both sides, before/after fresh
content hashes for every backend, and exact caller entrypoints in isolated writable
state with production writes inaccessible. Snapshotting does not grant session rights.
Current public-only adapter cannot serve private candidates; no private adapter exists
in this packet. Preserve unavailable; do not substitute legacy roots or operator rights.

Grade source presence, candidate retrieval, eligible revision-bound bounded supporting
passage, and final assertion/attributed-uncertainty/decline separately. Expected doc ID
with no fact must never pass passage/correctness. That negative and stale generation,
same-path content change, revoked context, off-window envelope canary and unavailable
backend controls are **specified, not executed**. Policy exclusion, healthy ranking
miss, disconnected ingestion and unknown have separate evidence requirements. Full
legacy corpus versus two-section public projection is asymmetric, not public parity.
No fact-loss, correctness, latency or public-eligibility metric is established.

## Preservation and actual checks

Private before receipt captures 295 prior artifact paths plus existing source sets,
selected caller/config/registry/two-section pilot, production HEAD/status/diff and11
dirty fingerprints, API PID38899 command/listening socket. Reused preservation helper
was inspected before use; it hashes files and runs only git/ps/lsof observations.
44 code files are additionally content/size/mtime-bound after inspection and before
packet/docs; that later baseline is not retroactive start proof. Parent alone owns
HEARTBEAT/notifier; neither edited nor attested unchanged by worker.

Actual checks: data-only packet binding/status/query/rubric checks, preservation
comparisons and git diff checks; no reader/model/probe, harness control, implementation,
full Python or Node test run. Early truncated control/discovery output and failed
path/glob lookups are disclosed privately; no source-reading credit claimed here.
Old receipts/failures/corrections/originals/quarantine and19prior saved negative controls
remain intact. All32summaries partial/mixed;301/301read,0unread,184mixed tasks,
1206findings,0promoted,unique claims null unchanged. Only this report and append-only
RESUME are committed. Private evidence manifest and checkpoint bind exact revisions.

No imports/reimports, rebuilds, restarts/deployment, public/source-rights expansion,
promotion, primary reader/routing/config/voice changes, destruction or U5. Original
conditional18–30active-hour estimate is historical conditional only, not a new ETA.
All broader claim/passage/integration/capture/shadow/voice/live-table/retirement gates
remain. Stop after audit20 for parent verification; no chained execution.
