# Native integration capability checkpoint

Inspected 2026-10-31 against installed OpenClaw 2026.9.8 / `4d94a9f`.
This is an evidence log, not a claim that U2 has passed.

## Established

- Native local semantic recall works through the existing OpenClaw tool and CLI.
  Three operator-CLI probes are saved privately under the U0 evaluation directory.
  CLI end-to-end median 5.7311s / maximum 6.2993s, n=3 (includes process startup;
  NOT a warm engine latency estimate). A new per-query CLI subprocess would exceed
  the proposed 2s campaign target; use a persistent adapter for the live path.
- Public external-provider registration exists: derive types from
  `MemoryPluginCapability`, register `providerRuntime`.
  Reference: OpenClaw `docs/plugins/sdk-overview/memory-and-context.md:145`.
- Consuming the active engine through `getActiveMemoryProvider` is a **private-local**
  API, not the public registration API. Reference: `src/plugin-sdk/memory-host-search.ts:50`
  and `docs/plugins/sdk-subpaths.md` entry for `memory-host-search`.
- Native authority separates operator, host and session callers. Session audience is
  host-minted and revocable; owner-private vs conversation is not inferred from sender IDs.
  Reference: `src/plugins/memory-provider-types.ts`, documented audience contract.
- `memory.search` v2 / `memory.get` Gateway RPCs are authenticated **operator** reads.
  The handler captures operator scopes; it is not a public/session-bound relay. Reference:
  `src/gateway/server-methods/memory-provider.ts:103` and `:177`.
- `extraPaths` supports direct authoritative file paths and patterns, skips symlinks.
  It indexes notes; it does not establish document visibility. Reference:
  `docs/reference/memory-config.md:450`.

## Integration decision / next experiment

Do not proxy the main agent's operator search into public voice/chat. Do not pretend a
local `AccessContext` is host-issued session authority. Preserve existing session tools
and their lifecycle/visibility checks; standalone service declares sessions unavailable.

First test an isolated, public-only native partition over explicitly reviewed authoritative
files, using a separate config/state/workspace and native index. No sessions/private notes
in this partition. Do not alter production config or use guessed private session IDs.
If consumption requires the private-local facade, put the version-pinned dependency in
ONE adapter, document the exact revision, and fail on incompatible runtime rather than
copying OpenClaw search code. A separate public partition may be read with local operator
authority because its ENTIRE eligible corpus is public, not because operator rights can
be downgraded by filtering returned snippets. Still revalidate references before reads.

The final OpenClaw tool-side adapter must obtain real trusted turn context. Its integration
shape is still unproven. Public provider registration alone does not prove one can safely
wrap/chain the existing selected memory owner. Test before choosing a slot replacement.

## Additional source-policy finding

`NPCs/Tom-Erlichman.md` combines established current status with an explicitly unapproved
generated background and a GM-draft build. A published page is therefore NOT equivalent
to every claim being confirmed. Keep this pilot page GM/provisional until section-level
status/provenance is represented. Do not auto-promote the whole wiki or indiscriminately
label every campaign result `confirmed`/`SR3`. This is a U1/U2 acceptance requirement,
not an excuse to delete the draft or rewrite campaign canon during infrastructure work.

## Unproven / do not claim

- A live caller-bound native lease used by the shared service.
- Public wiki classification, public-native partition or semantic parity.
- Unified equipment/rules routing or cross-caller agreement.
- Durable-fact import/capture receipts and live voice behavior.

## 2026-10-31: isolated public-partition spike proven (not U2 cutover)

U1 now uses registry schema v2; see `SOURCE-APPROVALS.md`. A single reviewed public
section from the mixed pilot page is projected into a new disposable index input. Its
page-level provisional status remains unchanged; GM background/build never enter the
partition. Authoritative wiki files were not edited. Full source/view eligibility is
validated before and after the subprocess, with the registry reloaded after I/O.

The installed `getActiveMemoryProvider` successfully opens a caller-bound **operator**
lease in an isolated state/config/workspace. Installed memory-core reports adapter
`legacy`: the neutral facade adapts its existing native builtin hybrid engine, rather
than exposing a new `providerRuntime`. Do not call this a public supported API or a
host-minted session lease. The facade advertises support for memory and sessions, even
when its configured/indexed source set is memory-only. Capability is not corpus membership.

### Embedding dependency and isolation

Minimal memory-core-only configuration cannot resolve `provider: local`; that adapter is
registered by the llama-cpp plugin. Loading its managed configuration can prepare/reconcile
services, which is unnecessary for a read-only retrieval experiment. Instead the isolated
partition uses documented `provider: openai-compatible` pointed at the already-running
loopback embedding endpoint, with the same EmbeddingGemma model, `fallback: none`, no
managed models configuration, no extraPaths and session/cross-conversation recall disabled.
No chat credential, production configuration copy, new plugin installation, daemon restart
or live memory-index rebuild is needed. The separately built index has its own provider
identity; it must not be overlaid on the live index.

### Checks and observed contract mismatch

- Native health proves builtin hybrid, FTS ready, complete vector index (768 dimensions),
  one input file / two chunks, and indexed sources exactly `memory`.
- Three queries repeated three times exercise entity, paraphrase and excluded-background
  wording. All native references stay within the one approved projection; native bounded
  get succeeds. A negative/background query may still return related public text; this is
  NOT evidence that the asked-about draft fact is public, confirmed or answered.
- Session search returns no hits; traversal, outside-workspace and missing direct reads
  are denied/not_found. Revoking the lease rejects later calls; teardown closes the lease.
- Native bounded get appends a continuation notice outside the structured source-line
  count. Validate `from`/`lines` and the exact source prefix, not total response newlines.
- **Raw native hybrid search does not strictly honor minScore.** The implementation in
  `extensions/memory-core/src/memory/hybrid.ts:270` intentionally admits lexical fallback
  below the requested threshold. Its legacy neutral facade passes those results through.
  `unification/native_contract.mjs` supplies a strict final score filter at our boundary;
  finite scores meeting the requested threshold only. The raw mismatch stays in the
  evidence report. This is ordering-contract enforcement, NOT an answer-confidence gate.
  Do not change production engine ranking to fix the isolated consumer.

Private dated partition directories and reports are referenced by STATE. Earlier failed
experiments remain preserved; subsequent attempts archive reports rather than overwrite
the only failure record. Small-corpus timings are experimental, not full-wiki p95 claims.

### Remaining U2 work / exact handoff

Build a persistent adapter using this pinned private-local facade and public partition.
It must validate source/approval generation before and after every operation, normalize
minScore, map projection references/citations back to authoritative section/revision,
fail explicitly on stale/unavailable runtime, respect host revocation and budgets, and
return honest partial coverage. Do not infer automaticRecall eligibility or session rights.
Then add exact SR3 specialist adapters and fixed-question shadow/nonregression evaluations.
The Python MemoryService hybrid path remains **unavailable** until that integration exists;
this successful standalone spike is not a claim that chat/CLI/voice share native recall yet.
