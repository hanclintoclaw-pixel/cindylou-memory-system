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
