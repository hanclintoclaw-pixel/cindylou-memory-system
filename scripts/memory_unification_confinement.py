#!/usr/bin/env python3
"""Explicitly opted-in fixed synthetic confinement proof; no real reader runner."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unification.confinement import run_synthetic_confinement


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--enable-synthetic', action='store_true')
    ap.add_argument('--scratch-parent')
    args = ap.parse_args()
    if args.enable_synthetic and not args.scratch_parent:
        ap.error('--enable-synthetic requires --scratch-parent')
    result = run_synthetic_confinement(args.scratch_parent, enabled=args.enable_synthetic)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'synthetic-proof-passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
