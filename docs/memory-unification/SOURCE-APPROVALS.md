# Revision- and section-bound source approvals

Isolated contract version 1; trusted registry schema **2**. No production caller uses it.
The former v1 blanket-path registry is rejected, not implicitly upgraded.

Each source declares its namespace, absolute canonical root and domain. Each approved
Markdown file declares its **complete-file SHA-256**, with one or more explicit,
non-overlapping, inclusive 1-based line ranges. Each section has an immutable identifier,
visibility, claim status, authority and optional originating evidence group/conversation.
Unknown visibility/status defaults operator/provisional, not public/confirmed.

```json
{
  "version": 2,
  "coverage": "partial",
  "sources": [{
    "namespace": "wiki",
    "root": "/absolute/authoritative/wiki",
    "domain": "campaign",
    "approvals": [{
      "path": "NPCs/Example.md",
      "revision": "<64 lowercase SHA-256 hex characters>",
      "sections": [{
        "section_id": "known",
        "start_line": 10,
        "end_line": 18,
        "visibility": "public",
        "status": "provisional",
        "authority": "campaign-record"
      }]
    }]
  }]
}
```

The example is schematic; its placeholder hash is deliberately invalid. A trusted local
reviewer creates approvals after reading the actual enclosing section and claim status.
There is no public request parameter that grants approval or elevated audience.

## Search/read behavior

- Any file edit invalidates approval, even a fresh search or get without a supplied old
  revision. Explicit `stale` is not an empty success; re-review the new revision.
- Denied/unreviewed sections do not reach lexical ranking, excerpts or result counts.
- Stable section references are `namespace/path.md#section-id`; guessed private sections
  are denied. Whole-page aliases work only for a single section spanning the entire file.
- Search/get preserve `claim_status`; get's transport `status` remains `ok`/denied/stale.
  A public provisional/disputed passage does not become confirmed through retrieval.
- Excerpts/citations retain source line numbers and full-file revision. Get bounds are
  section-relative; `source_line` maps the returned text back to the authoritative page.
- Sections of one file share their originating file's evidence group by default. A
  derivative view may explicitly retain its original evidence group; copies do not vote.
- Policy/context are rechecked after I/O and selected references after lexical ranking.
  Revocation, symlinks, traversal and changed approvals fail closed.

## Native index inputs

Native file indexing cannot safely ingest a mixed public/GM file as-is. `partition.py`
builds a **new disposable public-only projection generation**, not another canonical
corpus. Only reviewed public ranges are copied; all claims remain owned by original files.
The private map records exact section references, revision, range, status and projection hash.
No generated facts, status promotions or authoritative source edits occur.

Validate the complete source/view set both before and after native calls, reloading the
trusted registry after I/O. Any edit, revocation, classification/coverage change, modified
projection or unexpected workspace file requires a new generation. This checks root
USER.md/MEMORY.md as well as `memory/`, since native admission can scan both.
These checks protect the experiment's boundary; a production persistent adapter still
needs locking/invalidation, resource limits and trusted host integration (U2/U4).
