#!/usr/bin/env python3
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / '01_ingestion' / 'ingest_wordpress_gdocs.py'), run_name='__main__')
