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
