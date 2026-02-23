#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / '03_organization' / 'process_entity_queue.py'), run_name='__main__')
