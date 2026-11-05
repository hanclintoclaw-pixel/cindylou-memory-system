# Memory unification: start here

**One front desk, not one database to rule them all.**

Cindy has several ways to find and save information. The proposal is to
give those tools a shared set of rules: where truth lives, who may see it, how to
cite it, and what “remembered” actually means. Original sources stay authoritative;
search indexes remain replaceable. SR3 rules/equipment tools stay.

## Choose your explanation

- **[ELI5: the library story](ELI5.md)** — the idea, a diagram, and what works today.
- **[ELI10: follow a question and a new fact](ELI10.md)** — read/write diagrams,
  responsibilities, difficult edges, tradeoffs, and review questions.

## Status at November 4, 2026

This is **an unfinished integration project**, not a completed replacement.
Shared-service and capture code exists. Controlled pilots demonstrated a small
public search collection and import of 17 private records. A separate optional
public tool was deployed for two approved sections; that historical result is
not a claim of current liveness or broad rollout.

Connecting ordinary requests safely to the real host/workers is unfinished.
Full-source retrieval quality, caller migration, recovery, and voice/game-table
acceptance remain open. Existing routes have not all been replaced.

## A practical architecture review

Read ELI5, then ELI10. Discuss the review questions there **before** diving into
the implementation history. For evidence, follow:

- [Design goals and acceptance criteria](PLAN.md#goal-and-invariants)
- [Existing public-only search connection](ADAPTER-DESIGN.md)
- [Capture and controlled import](CAPTURE-AND-ROLLOUT.md)
- [Historical optional-tool deployment](U4-TOOL-CANARY.md)
- [Latest unfinished host-integration plan](U4-UPSTREAM-OWNERSHIP-SEAM-PLAN.md)

These guides explain the design, not certify readiness.
