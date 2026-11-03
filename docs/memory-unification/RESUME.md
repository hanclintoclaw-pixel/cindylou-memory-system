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

The fourth batch adds a reproducible session-passage comparator and advances content
review to 195/301 files; see `U4-SESSION-LINEAGE-REVIEW.md`. Mechanical tracing of all
58 session-note files / 59 chunks is NOT content clearance or PDF verification.
Imported scan headings are generated metadata, not human date evidence. STATE links
the v2 mechanical report, cumulative annotations, preservation and tests. Continue
the 24 unread scanned-note derivatives / remaining summary comparisons and 82
general-rules derivatives without changing primary readers, approvals or sources.

The next invocation adds 24 scan-note and 18 small general-file readings: current
content review is 237/301, with 64 unread and 120 mixed/unresolved source reviews.
See `U4-SCAN-AND-RULES-TRIAGE.md`. All 32 substantive summaries have only partial
extraction comparisons. The general tier is multi-megabyte citation aggregates,
not merely short profiles. STATE links a mechanical 164-general-facet inventory
(including 82 previously reviewed placeholder facets), bounded read windows and
ten unpaginated prefix comparisons to four imported campaign/homebrew texts.
Those passage comparisons do not count as full readings of the larger aggregates.
The inventory performs zero semantic reviews and its embedded source references
are not automatically opened or admitted. Retain the initial parser rejection and
truncation limits; continue STATE.next_action without imports, live probes or rebuilds.

The subsequent bounded rules-lineage pass advances content review to 242/301,
with 59 unread and 125 mixed/unresolved files; see `U4-RULES-EXCERPT-LINEAGE.md`.
Only five aggregates have the new six-original OCR trace: 289 exact substring
locations, three unmapped WordPress rows. Failed global attempts (missing targets
and alternate reference paths) remain retained, not a global-lineage success.
Five context/page-tail readings reveal attribution traps and unequal OCR/printed
page labels; no global offset, edition or rules-authority clearance follows.
STATE points to the newest validated cumulative artifacts and preservation evidence.

The next context/alias pass advances content review to 250/301, with 51 unread
and 133 reviewed files still mixed/unresolved; see
`U4-AGGREGATE-CONTEXT-AND-ALIASES.md`. Eight whole files were actually read in 29
bounded windows. Four current-route aggregates have 404 exact page-bound OCR
substring rows plus two imported-NPC prefixes, not rules/claim clearance. Five
original contexts include a clipped sentence whose continuation changes an
apparent Matrix access prohibition into publicity guidance. The old Critters
workspace path is absent: all 132 references remain unresolved, zero aliases
admitted. Optional aliases require explicit selection and complete current-byte
identity; they do not verify historical identity. Continue STATE.next_action,
preserving prior failures, originals, quarantine and all deployment boundaries.

The next lexical-contamination pass advances review to 256/301 files, with 45
unread and 139 reviewed mixed/unresolved; see `U4-LEXICAL-CONTAMINATION-REVIEW.md`.
Six full files were read in 12 bounded windows. All 155 selected citation rows
copy exactly from six explicitly routed OCR originals, yet three context-checked
IC hits are merely broken-word suffixes. Five actual context readings distinguish
those from intrusion countermeasures, a named Humanis worm from the organization,
and a spirit-host table from Matrix mechanics. STATE links source-bound review,
CLI parity, 32 targeted passing tests and selected preservation receipts. No new
implementation, full-suite rerun, source admission or reader cutover is implied.


The 2026-11-03 resume verified that Batch9 was already complete, then executed
only STATE.next_action's six different unread candidates as Batch10; see
`U4-ADJECTIVE-METAPHOR-ATTRIBUTION-REVIEW.md`. Six new whole-file readings took
18 bounded windows, with six original OCR contexts. Cumulative content review
is 262/301, with 39 unread, 145 reviewed mixed/unresolved, 184 source tasks and
556 findings; zero promoted, unique claims unassessed. Five explicitly routed
aggregates have 243 exact citation-row matches / 250 locations / five ambiguous
rows; Restore description's 55 original references stay unresolved and unopened.
Adjectives, metaphors, entertainment, NPC restrictions and explicit falsity
remain quarantined despite copy equality. Fresh 46 targeted tests pass; no code,
full-suite or Node rerun is implied. STATE links the new private evidence and
production/source/process preservation checks; historical Batch9 receipts stay
retained without duplicate credit. Continue STATE.next_action, not earlier counts.


The next bounded continuation is Batch11; see
`U4-POLYSEMY-AND-SCENARIO-REVIEW.md`. Six new whole-file readings took 22
revision-bound windows, with eight OCR contexts plus five page-tail windows.
Current cumulative review: 268/301, 33 unread, 151 reviewed mixed/unresolved,
184 source follow-ups, 610 findings; zero promoted, unique claims unassessed.
Four explicitly routed aggregates yield 279 exact citation rows / 281 locations /
two ambiguous rows, with actual CLI/module parity. The two descriptions retain
148 unresolved unopened references. Polysemy, infected/variant subjects, fictional
listings, contested testimony, rumored holdings, forecasts and GM scenario premises
stay distinct and quarantined. Fresh 46 targeted Python checks pass; no full-suite
or Node rerun. STATE links current receipts and exact next_action. Preserve all
prior failures/originals/quarantine, 32 partial summaries, 132 unresolved Critters
references, 23 unavailable labels, selected production fingerprints, active API
identity/socket and two-section pilot. No live reprobes or deployment changes.


The next bounded continuation is Batch12; see `U4-ROLE-AND-HARDWARE-REVIEW.md`.
Six new whole-file readings took 33 revision-bound windows, with eight original
OCR contexts and four additional tails. Current cumulative review: 274/301,
27 unread, 157 reviewed mixed/unresolved, 184 source follow-ups, 670 findings;
zero promoted, unique claims unassessed. Only Deck passed the explicit-route
preflight for tracing: 120 exact rows, 123 matching locations, two ambiguous
rows, with actual CLI/module parity. Five descriptions retain 629 unresolved
unopened references. Subject/role distinctions include signatures, metaphor,
nautical language, conditional creature effects, ordinary proficiency and
historical brands versus current ownership; copy equality does not clear them.
46 targeted Python tests pass; no implementation/full-suite/Node rerun. STATE
links private source-bound coverage, annotations, validation, context, preflight,
CLI, tests, failure and selected preservation receipts. Earlier attestations,
32 partial summaries, 132 missing Critters references, 23 unavailable labels,
originals, quarantine and prior failures remain. Production fingerprints, selected
caller/config/pilot inputs and API identity/socket are preserved without live
reprobes. HEARTBEAT stays unchanged. No deployment/routing/voice/source-rights,
import/rebuild, promotion or U5 change; retain prior estimate and open gates.
Stop after this batch and continue only STATE.next_action next invocation.


The next bounded continuation is Batch13; see
`U4-CONDITIONAL-AND-SUBJECT-REVIEW.md`. Six new whole-file readings took 40
revision-bound contiguous windows; 10 original OCR contexts, 8 additional tails and 4
supplemental heading/continuation windows were actually read. Current cumulative
review: 280/301, 21 unread, 163 reviewed mixed/unresolved, 184 source follow-ups,
739 findings (69 new), zero promoted, unique claims unassessed. Only Spell passed
explicit-route preflight: 142 exact rows/145 locations/two ambiguous rows, with actual
CLI/module parity. Five descriptions retain 776 unresolved unopened references;
zero aliases admitted. Ordinary spelling, figurative language, signatures, animal
subjects, character-building currencies, sport-specific restrictions and conditional
GM material remain distinct from general mechanics; corporate disguise, historical
ownership, names, product brands, allegations and scenarios stay attributed.
Suspicious OCR expansion stays unverified; copy equality is not rules/edition/page,
PDF-image, claim/canon/disclosure/retrieval clearance. Fresh 46 targeted Python tests
pass; no implementation/full-suite/Node rerun. All prior 274 annotations, 32 partial
summaries, 132 missing Critters references, 23 unavailable labels,prior failures,
originals and quarantine retained. Selected sources/production/caller/config/pilot
fingerprints, 141 prior artifact hashes and API PID 38899 command/socket preserved
without live reprobes. Read-only unavailable-rg failure and corrected adjacent-page
supplement metadata retained privately. HEARTBEAT unchanged. STATE links exact
private receipts and next_action. Retain original conditional 18–30 active-hour
estimate and unfinished supporting-passage/paired-answer/eligible-source/primary-reader/
capture/shadow/voice/live-table/retirement gates. No imports/rebuilds/restarts,
promotions, public expansion, routing/config/voice/source-rights or U5 changes.
Stop after Batch 13; parent verifies/reports; Batch 14 not started.


The next bounded continuation is Batch14; see `U4-METATYPE-AND-IDENTITY-REVIEW.md`.
Six description aggregates were fully read in56 revision-bound contiguous windows.
Current cumulative review:286/301 files,15 unread,169 reviewed mixed/unresolved,
184 source follow-ups,831 findings(92 new),zero promoted,unique claims unassessed.
Explicit-route preflight found no consistent file subset:all1330 embedded references
remain unresolved/unopened;no tracing,CLI/module trace-parity or aliases claimed.
Four independently selected current Critters OCR-page comparisons were actually read
in nine substantive windows plus four terminal-blank supplements. They distinguish
infected subjects,predator/prey size,and resemblance;they do not resolve old paths,
prove historical copies,or admit rules. Failed comparison-plan paths and coverage
clarification remain privately evidenced. Metatypes,individuals,personae,avatars,
brands,metaphor,cultural chronology and conditional adventure outcomes stay separate.
Actual review-validator CLI/module equality and46 targeted Python tests pass;no
implementation/full-suite/Node rerun. Prior280 annotations,32 partial summaries,
132 missing Critters references,23 unavailable labels,prior failures/originals/quarantine,
suspicious extraction and corrected Batch13 adjacent-page metadata remain retained.
All selected queued/original/import/OCR/prior-artifact/production/caller/config/pilot
fingerprints and API PID38899 command/socket preserved without live reprobes.
HEARTBEAT unchanged;no import/rebuild/restart,deployment,promotion,public expansion,
primary reader/config/routing/voice/source-rights or U5 change. Keep original conditional
18–30 active-hour estimate and all supporting-passage/paired-answer/eligible-source/
integration/capture/shadow/voice/live-table/retirement gates open. STATE links current
private receipts and exact next_action. Stop after Batch14;parent verifies/reports;
Batch15 not started.

The next bounded continuation is Batch15;see `U4-ENTITY-AND-COUNTERMEASURE-REVIEW.md`.
Recovery preserved interrupted-worker artifacts,reused valid plans and gave partial
reads zero credit. Six unread aggregates fully read in93 contiguous revision-bound
windows. Cumulative292/301 reviewed,9 unread,175 mixed/unresolved,184 source follow-ups,
954 findings(123 new),zero promoted,unique claims unassessed;prior286 annotations unchanged.
Dragon-only trace:288 exact rows/292 locations/one ambiguous row;actual CLI/module parity.
Five descriptions1900 references unresolved/unopened;zero aliases. Seventeen planned OCR
contexts,two adjacent continuation windows and eight terminal-blank supplements cover nine
page intervals;four current Critters comparisons are not old-path aliases/copy proof.
Subject/form/infection/brand/corporate relation/attribution/adventure contingency/IC token
contamination/conditional GM premises remain separate and quarantined. Actual review-validator
CLI/module equality and46 targeted Python tests pass;no implementation/full-suite/Node rerun.
Postwrite diagnostic KeyError,failed documentation patch and terminal-blank clarification
retained;no replayed writes,source repair or guessed mapping. Prior32 partial summaries,
132 missing Critters references,23 unavailable labels,failures/corrections,originals/quarantine,
suspicious extraction and corrected Batch13 metadata retained. Selected source/production/
caller/config/registry/pilot hashes,API PID38899 command/socket and generic HEARTBEAT unchanged.
All188 prior artifacts checked before docs;187 unchanged afterward,only authorized RESUME
append with prior git revision retained. No live reprobes,imports/rebuilds/restarts,deployment,promotion,
public/source-rights expansion,primary reader/routing/config/voice or U5 change. Retain original
conditional18–30 active-hour estimate and all supporting-passage/claim-level paired-answer/
eligible-source/integration/capture/shadow/voice/live-table/retirement gates. STATE links exact
private receipts and next_action. Stop after Batch15;parent verifies/reports;Batch16 not started.
