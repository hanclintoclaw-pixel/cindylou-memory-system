#!/usr/bin/env python3
"""Opt-in scratch synthetic controls; real reader lanes always unavailable."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-synthetic', action='store_true')
    parser.add_argument('--lane', default='private-native', choices=['synthetic', 'private-native', 'legacy', 'native', 'model', 'http', 'tool'])
    parser.add_argument('--design', type=Path)
    parser.add_argument('--design-sha256')
    parser.add_argument('--scratch-parent', type=Path)
    args = parser.parse_args(argv)
    # Gate before even loading local scaffolding, reading inputs or creating output.
    if not args.enable_synthetic or args.lane != 'synthetic':
        print(json.dumps({'status': 'unavailable', 'reason': 'default-off' if not args.enable_synthetic else 'real-execution-not-implemented',
                          'real_reader_execution': False}))
        return 0
    if not all((args.design, args.design_sha256, args.scratch_parent)):
        parser.error('synthetic controls require pinned design and private scratch parent')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from unification.isolation import (ScratchWorkspace, SyntheticAuthority,
        SyntheticSupervisor, load_prepared_cases, require_generation, scratch_generation)
    before = load_prepared_cases(args.design, args.design_sha256)
    protected = [Path(__file__).resolve().parents[1], *map(Path, before['source_revisions'])]
    with ScratchWorkspace(args.scratch_parent, forbidden_roots=protected) as workspace:
        fixture = {'doc_id': 'synthetic/page', 'text': 'The fixture token is cobalt wren.'}
        for name in ['source', 'code', 'registry', 'partition']:
            workspace.write_json(name + '.json', fixture if name == 'source' else {'synthetic': name})
        generation = scratch_generation(workspace, [workspace.path / (n + '.json') for n in ['source', 'code', 'registry', 'partition']])
        authority = SyntheticAuthority()
        context = authority.mint()
        supervisor = SyntheticSupervisor(workspace, authority, generation, enabled=True)
        expected = {'doc_id': 'synthetic/page', 'revision': generation[str(workspace.path / 'source.json')]['sha256'], 'required_terms': ['cobalt wren']}
        hit = {'doc_id': expected['doc_id']}
        good = {'status': 'ok', 'results': [hit], 'passage': {'doc_id': expected['doc_id'], 'revision': expected['revision'],
                'eligible': True, 'start_line': 1, 'end_line': 1, 'text': fixture['text']}}
        query = 'Synthetic fixture token?'
        attempt = supervisor.begin(query, context)
        positive = supervisor.finish(attempt, query, context, expected, {'legacy': good, 'unified': good})
        attempt = supervisor.begin(query, context)
        negative = supervisor.finish(attempt, query, context, expected, {'legacy': {'status': 'ok', 'results': [hit]},
                                                                 'unified': {'status': 'ok', 'results': [hit]}})
        assert all(g['eligible_bounded_passage'] for g in positive['grades'].values())
        assert not any(g['eligible_bounded_passage'] for g in negative['grades'].values())
        after = load_prepared_cases(args.design, args.design_sha256)
        if before != after:
            raise ValueError('private preparation generation changed')
        require_generation(workspace, generation)
        receipt = {'kind': 'synthetic-only-and-private-unavailable', 'private_inventory': before,
                   'positive_control': positive, 'doc_id_without_fact_control': negative,
                   'private_inputs_unchanged': True, 'production_write_denial_proven': False,
                   'retrieval_quality_measured': False, 'real_reader_execution': False,
                   'limits': 'Cooperative scratch output guards only; no OS sandbox, host authority, compiled-provider or descendant isolation proof.'}
        saved = workspace.write_json('controls.private.json', receipt)
        print(json.dumps({'status': 'synthetic-controls-only', 'private_cases_unavailable': before['case_count'],
                          'output_directory': str(workspace.path), 'receipt': saved, 'real_reader_execution': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
