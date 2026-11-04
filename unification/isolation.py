"""Default-off evaluation scaffolding. NOT an OS sandbox or a reader adapter.

Only synthetic controls can run. Private/native/legacy execution has no dispatch
implementation, even if a caller supplies convincing-looking proof fields.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time


class Rejected(ValueError):
    """An input, generation or cooperative scratch-output guard failed."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def execution_gate(*, enabled=False, lane="private-native"):
    """Run before opening inputs or considering any adapter imports/processes."""
    if not enabled:
        return {"status": "unavailable", "reason": "default-off"}
    if lane != "synthetic":
        return {"status": "unavailable", "reason": "real-execution-not-implemented",
                "remaining_gates": ["host-issued-revocable-authority",
                    "source-to-compiled-provider-worker-identities",
                    "production-write-denial-and-descendant-settlement"]}
    return {"status": "synthetic-only", "real_reader_execution": False}


def canonical(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise Rejected("absolute non-traversing path required")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Rejected("symlink paths forbidden")
    return path.resolve(strict=True)


class ScratchWorkspace:
    """Cooperative immutable-output guard; does not confine arbitrary Python code.

    Creates a fresh owner-only child of an explicitly designated private parent.
    Single-component names and dir-fd/O_NOFOLLOW writes prevent path escapes and
    replacement. No production reader, code loading, shell or network is offered.
    """
    def __init__(self, parent, *, forbidden_roots=()):
        parent = canonical(parent)
        info = parent.stat()
        if not parent.is_dir() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Rejected("scratch parent must be owned directory mode 0700")
        for root in forbidden_roots:
            root = canonical(root)
            if parent == root or root in parent.parents or parent in root.parents:
                raise Rejected("scratch/source/protected paths overlap")
        self.path = parent / ("synthetic-" + secrets.token_hex(12))
        self.path.mkdir(mode=0o700)
        self._fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._identity = (os.fstat(self._fd).st_dev, os.fstat(self._fd).st_ino)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def write_json(self, name, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", name) or name in (".", ".."):
            raise Rejected("single safe JSON filename required")
        if self._fd is None:
            raise Rejected("workspace closed")
        current = self.path.lstat()
        if stat.S_ISLNK(current.st_mode) or (current.st_dev, current.st_ino) != self._identity:
            raise Rejected("workspace path identity changed")
        raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self._fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(self._fd)
        return {"name": name, "sha256": digest(raw), "bytes": len(raw)}


def scratch_generation(workspace, paths):
    """Fresh byte+mtime identities of explicitly enumerated scratch files only."""
    result = {}
    root = canonical(workspace.path)
    for path in paths:
        path = canonical(path)
        if root not in path.parents or not path.is_file():
            raise Rejected("synthetic generation must use owned scratch files")
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise Rejected("file changed during fingerprint")
        result[str(path)] = {"sha256": digest(raw), "bytes": len(raw), "mtime_ns": after.st_mtime_ns}
    if not result:
        raise Rejected("empty generation")
    return result


def require_generation(workspace, expected):
    if scratch_generation(workspace, expected) != expected:
        raise Rejected("source/code/registry/partition generation drift")


class SyntheticAuthority:
    """Revocable local test tokens. These are NEVER host/session authority."""
    def __init__(self):
        self._tokens = {}

    def mint(self, ttl=60):
        if ttl <= 0:
            raise Rejected("positive test lifetime required")
        token = object()
        self._tokens[token] = time.monotonic() + ttl
        return token

    def revoke(self, token):
        self._tokens.pop(token, None)

    def require(self, token):
        try:
            valid = self._tokens.get(token, 0) > time.monotonic()
        except TypeError:
            valid = False
        if not valid:
            raise Rejected("unknown/revoked/expired synthetic context")


def synthetic_grade(expected, response):
    """Literal scratch-only rubric, not a semantic grader for private candidates.

    A document ID alone is candidate retrieval, not bounded fact support. Only a
    revision-matched eligible bounded passage can meet this synthetic rubric.
    Final model-answer correctness and migration loss always remain unassessed.
    """
    category = response.get("status", "unknown")
    if category not in {"ok", "policy-excluded", "ranking-miss", "ingestion-gap", "unavailable", "unknown"}:
        raise Rejected("unrecognized backend state")
    hits = response.get("results", [])
    candidate = any(h.get("doc_id") == expected["doc_id"] for h in hits)
    passage = response.get("passage", {})
    text = passage.get("text", "")
    bounded = (type(passage.get("start_line")) is int and type(passage.get("end_line")) is int
               and 1 <= passage["start_line"] <= passage["end_line"]
               and passage["end_line"] - passage["start_line"] < 80
               and len(text) <= 6000)
    supported = (category == "ok" and candidate and passage.get("eligible") is True
                 and passage.get("doc_id") == expected["doc_id"]
                 and passage.get("revision") == expected["revision"] and bounded
                 and bool(expected["required_terms"])
                 and all(term in text for term in expected["required_terms"]))
    return {"backend_state": category, "candidate_retrieval": candidate,
            "eligible_bounded_passage": supported,
            "synthetic_literal_support": "pass" if supported else "not-established",
            "final_answer_correctness": "not-assessed", "loss": "unknown"}


@dataclass(frozen=True)
class Attempt:
    identity: str
    query_sha256: str


class SyntheticSupervisor:
    """Two-phase, same-context/query control runner; no callable reader dispatch."""
    def __init__(self, workspace, authority, generation, *, enabled=False):
        if execution_gate(enabled=enabled, lane="synthetic")["status"] != "synthetic-only":
            raise Rejected("default-off")
        self.workspace, self.authority = workspace, authority
        # Do not retain caller-mutable generation dictionaries.
        self.generation = json.loads(json.dumps(generation))
        self._pending = {}

    def begin(self, query, context):
        self.authority.require(context)
        require_generation(self.workspace, self.generation)
        attempt = Attempt(secrets.token_hex(16), digest(query.encode()))
        self._pending[attempt.identity] = (context, attempt.query_sha256)
        return attempt

    def finish(self, attempt, query, context, expected, responses):
        pending = self._pending.pop(attempt.identity, None)
        if pending is None or pending[0] is not context or pending[1] != digest(query.encode()) or pending[1] != attempt.query_sha256:
            raise Rejected("attempt/context/query mismatch or replay")
        self.authority.require(context)
        require_generation(self.workspace, self.generation)
        if set(responses) != {"legacy", "unified"}:
            raise Rejected("exactly two synthetic sides required")
        grades = {side: synthetic_grade(expected, response) for side, response in responses.items()}
        self.authority.require(context)
        require_generation(self.workspace, self.generation)
        return {"kind": "synthetic-harness-control-only", "query_sha256": pending[1],
                "generation": self.generation, "grades": grades,
                "descendants_started": 0, "real_reader_execution": False,
                "host_authority_proven": False, "production_write_denial_proven": False}


def load_prepared_cases(path, expected_sha256):
    """Read-only consumption of the pinned private nineteen-case preparation.

    Verifies packet and source bytes, not source truth, eligibility or ingestion.
    Returns metadata-only disposition; never runs the synthetic literal grader on
    unresolved historical claims or interprets their rubrics as accepted facts.
    """
    path = canonical(path)
    raw = path.read_bytes()
    if digest(raw) != expected_sha256:
        raise Rejected("prepared design drift")
    design = json.loads(raw)
    cases = design["cases"]
    ids = [c["case_id"] for c in cases]
    expected_ids = {f"CP18-{n:02}" for n in range(1, 11)} | {f"CP19-{n:02}" for n in range(1, 10)}
    if len(cases) != 19 or set(ids) != expected_ids or len(set(ids)) != 19:
        raise Rejected("nineteen fixed case identities required")
    files = {str(path): expected_sha256}
    for packet, revision in design["packets"].items():
        files[str(canonical(packet))] = revision
    for case in cases:
        if digest(case["query"].encode()) != case["query_sha256"] or not case["expected_answer_rubric"] or not case["rubric_limits"]:
            raise Rejected("query/rubric drift")
        if case["retained_status"] != "private-provisional-unresolved-not-promoted":
            raise Rejected("private unresolved status required")
        for binding in [case["summary_binding"], *case["supporting_passages"]]:
            source = str(canonical(binding["path"]))
            revision = binding["revision"]
            if source in files and files[source] != revision:
                raise Rejected("conflicting source generation")
            files[source] = revision
    if len({c["originating_evidence_group"] for c in cases}) != 2 or design["unique_claims"] is not None or design["promoted"] != 0:
        raise Rejected("origin/status totals changed")
    for source, revision in files.items():
        if digest(Path(source).read_bytes()) != revision:
            raise Rejected("packet/source generation drift")
    return {"kind": "private-case-unavailable-inventory", "design_sha256": expected_sha256,
            "case_count": 19, "origin_groups": 2, "unique_claims": None, "promoted": 0,
            "source_revisions": files,
            "cases": [{"case_id": c["case_id"], "query_sha256": c["query_sha256"],
                       "retained_status": c["retained_status"],
                       "legacy": "unavailable", "unified": "unavailable",
                       "eligible_bounded_passage": "not-run",
                       "final_answer_correctness": "not-assessed", "loss": "unknown"} for c in cases]}
