"""Load a trusted local source manifest; never accept manifests from a remote request."""
from pathlib import Path
import json

from .policy import Registry, Source


def load_registry(path: Path) -> Registry:
    payload = json.loads(path.read_text())
    if payload.get('version') != 1 or not isinstance(payload.get('sources'),list):
        raise ValueError('unsupported registry schema')
    sources = []
    for entry in payload['sources']:
        if set(entry) - {'namespace','root','visibility','domain','status','approved',
                         'conversation_id','authority','evidence_group'}:
            raise ValueError('unknown registry field')
        if not isinstance(entry.get('approved'),list) or not all(isinstance(x,str) for x in entry['approved']):
            raise ValueError('explicit approved list required')
        root = Path(entry['root'])
        if not root.is_absolute():
            raise ValueError('registry root must be absolute')
        sources.append(Source(**{**entry,'root':root,'approved':frozenset(entry['approved'])}))
    return Registry(sources,coverage=payload.get('coverage','partial'))
