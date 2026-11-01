# Resume memory unification

1. Read `PLAN.md` and private
   `/Volumes/carbonite/claw/data/cindylou/runtime/memory-unification/STATE.json`.
2. Worktree: `/Users/hanclaw/claw/projects/cindylou/worktrees/memory-unification`.
   Confirm branch `memory-unification-20261031` and inspect ONLY task paths/status.
3. Read private `JOURNAL.md` for evidence/last tests. Check artifacts and receipts before
   rerunning anything. Do not repeat legacy-fact imports, restart production, or rebuild
   native indexes just because context was lost.
4. Execute STATE.next_action, then update STATE and journal before another batch.
   Use `python3 scripts/memory_unification_checkpoint.py --batch U1 --status in_progress
   --next-action '<concrete next action>' --note '<evidence and remaining work>'` for
   atomic state updates (add `--commit` and `--artifact name=/absolute/path` as needed).
5. A reset does not revoke the authorization to build. Do not require operator restatement.
   Respect each deployment/privacy gate and accurately preserve incomplete steps.

The plan is internal. Private baselines/results must not be copied to the campaign wiki.

## After the section-approval checkpoint

The trusted pilot registry now requires schema v2 (exact hash + explicit section ranges);
legacy v1 blanket approvals are rejected. Read `SOURCE-APPROVALS.md` and the latest native
spike section in `NATIVE-INTEGRATION.md`. Verification commands:

- `python3 -m unittest discover -s tests/unification -v`
- `node --test tests/unification/native_contract.test.mjs`

The public partition is a disposable index view, never a new canonical source. Its
loopback embedding transport does not manage/restart the existing service. Preserve
failed experiment reports. This spike paragraph is historical; read STATE for
current batch status rather than carrying its earlier U2-in-progress state forward.

## Current U4 preparation

U2 limited-pilot engineering and U3 private capture/import are committed. A separate
default-off public campaign CLI has been prepared and verified against the same
two-section native partition; see `U4-CLI-CANARY.md`. Exact current commit, private
receipt, tests, deployment boundary and next action are recorded in STATE/JOURNAL.
The separate CLI was subsequently approved and installed; see STATE and
`U4-CLI-CANARY.md` for its pinned release/installed receipt. Do not repeat
imports, source approvals or index generation on resume. Existing CLI/API/voice
routes remain unchanged; no U5 retirement is authorized.

The subsequent API listener was separately approved in request
`1566243029671485605` and started from a hash-checked, pinned release on
127.0.0.1:18091. Read `U4-API-CANARY.md` and STATE's active process/private receipt
before any restart. There is no autostart; verify current process identity and
authenticated health rather than assuming it survived. Do not infer permission
for primary API/browser/voice routing or broader sources from canary approval.
Checkpointing preserves active processes unless explicitly replaced or cleared;
use `--active-process '<JSON with positive pid>'` for a verified running instance
and `--clear-active-processes` only after verified shutdown.

The next tool-client preparation is documented in `U4-TOOL-CANARY.md`.
`unification.canary_tool` calls the approved API; the optional OpenClaw plugin
candidate remains separate from all primary routes. Read STATE for its pinned
release, actual verification/discovery receipts and pending deployment boundary.
Do not mistake isolated runtime discovery or the registration harness for live
Gateway installation. Preserve the complete release layout (Python modules plus
nested plugin), owner-only token, requester-scoped grant and invocation guards.

The separate optional tool was subsequently approved in `1566253226179690577`
and enabled at corrected pinned release `451748b`; see STATE for exact receipts.
Live operator RPC and disable/re-enable rollback passed, but a new Discord model
turn's admission/invocation remains to be observed. Captured plugin modules must
derive the adjacent Python release from host-selected original `api.source`, not
relocated `import.meta.url`. Do not revert to the initially prepared release or
change primary routing while expanding evidence.

Fresh Discord turn admission/search/revision-bound reads were subsequently
observed on 2026-11-01. The first private legacy content-review pass is in
`U4-DISCORD-AND-LEGACY-REVIEW.md`; STATE links the exact receipts and progress
projection. All 301 revisions were checked; 136 files content-reviewed is NOT
136 lineage-cleared sources: 44 of those remain unresolved/mixed. Do not repeat
the live operator-RPC checks or original imports to recover this state. Read the
progress projection and continue substantive source/lineage review without
public promotion, partition expansion or primary-reader/voice cutover.

The next continuation supersedes those historical review counts and corrects
filename-derived chronology; see `U4-LEGACY-REVIEW-CONTINUATION.md`. Read STATE's
latest progress artifact (166/301 content-reviewed at that checkpoint; 66 still
mixed/unresolved), not the first-pass annotation as the current review. Original
receipts remain retained. `REMAINING-WORK-ESTIMATE.md` records a conditional
18–30 active-hour planning range to a cutover-ready candidate, not a deployment
or final-retirement promise. Continue STATE.next_action without repeating imports,
canary probes or index builds.
