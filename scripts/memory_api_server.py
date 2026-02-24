#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / '05_serving' / 'memory_api_server.py'), run_name='__main__')
