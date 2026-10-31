"""Disposable public-only index inputs; authoritative files remain in their owners.

Never point native extraPaths at a mixed file. Materialize only exact approved public
sections, with a revision map. This view is NOT canon and must be revalidated before
and after any native operation; it must never silently survive source revocation.
"""
import hashlib
import json
from pathlib import Path

from .policy import AccessContext, Registry, StaleReference


def materialize_public(registry: Registry, target: Path) -> dict:
    # New generation only: no stale, orphaned input from an earlier run can remain.
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace = target/'workspace'
    notes = workspace/'memory'
    notes.mkdir(parents=True, mode=0o700)
    records = []
    for doc in registry.documents(AccessContext()):
        file_id = hashlib.sha256(doc.doc_id.encode()).hexdigest() + '.md'
        raw = doc.content.encode('utf-8')
        path = notes/file_id
        path.write_bytes(raw)
        path.chmod(0o600)
        records.append({'path': 'memory/'+file_id, 'sha256': hashlib.sha256(raw).hexdigest(),
                        'evidence': doc.evidence()})
    manifest = {'version':1, 'kind':'disposable-public-index-view',
                'coverage':registry.coverage, 'records':records}
    validate_public(registry, target, manifest)
    (target/'partition.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def validate_public(registry: Registry, target: Path, manifest: dict) -> None:
    expected = {}
    # Full-set comparison detects additions, removals, classification changes and
    # revision drift, not merely changes to whichever hit the backend returned.
    for doc in registry.documents(AccessContext()):
        expected[doc.doc_id] = doc
    seen = set()
    inputs = set()
    for record in manifest['records']:
        evidence = record['evidence']
        doc = expected.get(evidence['doc_id'])
        if doc is None or evidence != doc.evidence() or doc.doc_id in seen:
            raise StaleReference('public partition eligibility changed; rebuild required')
        seen.add(doc.doc_id)
        name = hashlib.sha256(doc.doc_id.encode()).hexdigest()+'.md'
        rel = 'memory/'+name
        if record['path'] != rel:
            raise StaleReference('invalid partition reference')
        path = target/'workspace'/rel
        if path.is_symlink() or path.resolve() != path.absolute():
            raise StaleReference('invalid partition path')
        raw = path.read_bytes()
        if raw != doc.content.encode('utf-8') or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise StaleReference('public partition content changed')
        inputs.add(path)
    if seen != set(expected):
        raise StaleReference('public partition coverage changed; rebuild required')
    # Only these inputs can exist anywhere in the isolated workspace. Native also
    # scans root USER.md/MEMORY.md, so checking just memory/*.md is insufficient.
    workspace = target/'workspace'
    actual = set()
    for path in workspace.rglob('*'):
        if path.is_symlink():
            raise StaleReference('invalid partition path')
        if path.is_file():
            actual.add(path)
    if inputs != actual:
        raise StaleReference('unexpected public partition input')
