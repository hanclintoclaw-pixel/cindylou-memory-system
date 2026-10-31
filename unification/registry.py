"""Trusted local revision-bound manifest; never deserialize a remote manifest."""
from pathlib import Path
import json

from .policy import Approval, Registry, Section, Source


def _fields(value, allowed):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('unknown registry field')


def load_registry(path: Path) -> Registry:
    payload = json.loads(path.read_text())
    _fields(payload, {'version', 'sources', 'coverage'})
    if payload.get('version') != 2 or not isinstance(payload.get('sources'), list):
        raise ValueError('unsupported registry schema; revision-bound v2 required')
    sources = []
    for entry in payload['sources']:
        _fields(entry, {'namespace', 'root', 'domain', 'approvals', 'evidence_group'})
        if not isinstance(entry.get('approvals'), list):
            raise ValueError('explicit approvals required')
        approvals = []
        for item in entry['approvals']:
            _fields(item, {'path', 'revision', 'sections'})
            if not isinstance(item.get('sections'), list):
                raise ValueError('explicit sections required')
            sections = []
            for section in item['sections']:
                _fields(section, {'section_id', 'start_line', 'end_line', 'visibility',
                                  'status', 'authority', 'evidence_group', 'conversation_id'})
                sections.append(Section(**section))
            approvals.append(Approval(item['path'], item['revision'], tuple(sections)))
        sources.append(Source(**{**entry, 'root': Path(entry['root']), 'approvals': tuple(approvals)}))
    return Registry(sources, coverage=payload.get('coverage', 'partial'))
