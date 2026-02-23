# Cindy Lou Memory System (Public Source)

This repository contains the source scripts used to ingest, process, and index campaign/memory artifacts for the Cindy Lou assistant workflow.

## Included
- `scripts/` automation scripts for ingestion, queue processing, OCR/index maintenance, and KB builds.

## Not Included (privacy/safety)
- `memory/` runtime memory and personal/campaign notes
- `logs/` execution logs
- `outputs/` generated artifacts
- local environments/secrets
- source corpora/PDF text dumps

## Quick start
```bash
python3 scripts/ingest_wordpress_gdocs.py
python3 scripts/process_entity_queue.py
python3 scripts/build_campaign_kb.py
python3 scripts/build_sr3_lore_kb.py
```

Adjust paths/configs in scripts for your environment.

## Canonical local layout
- Code: `/Users/hanclaw/claw/projects/cindylou/`
- Raw inputs: `/Volumes/carbonite/GDrive/cindylou/`
- Intermediates/cache: `/Volumes/carbonite/claw/data/cindylou/`
