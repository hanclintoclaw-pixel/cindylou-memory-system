#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / '03_organization' / 'build_entity_manifest.py'), run_name='__main__')
