# Cindy Lou Memory System

Staged data pipeline for ingestion, OCR cleanup, memory organization, caching, and serving.

## Repository Layout
- `01_ingestion/` raw ingestion and OCR runners
- `02_cleanup/` OCR harmonization and cleanup
- `03_organization/` knowledge/campaign memory builders
- `04_caching/` cache stage (reserved)
- `05_serving/` wiki/server runtime
- `config/` shared path configuration helper
- `scripts/` compatibility wrappers that forward to staged script locations
- `ARCHITECTURE.md` stage-by-stage flow

## Configuration
1. Copy `.env.example` to `.env`.
2. Override values as needed for your machine.

All Python scripts use `config/pipeline_paths.py` for path resolution.

## Run by Stage
Ingestion:
```bash
python3 01_ingestion/ingest_wordpress_gdocs.py
bash 01_ingestion/sr3_macos_ocr_runner.sh
bash 01_ingestion/sr3_deepseek_ocr_runner.sh
```

Cleanup:
```bash
python3 02_cleanup/harmonize_core_rulebook.py
bash 02_cleanup/harmonize_all_sr3.sh
```

Organization:
```bash
python3 03_organization/process_entity_queue.py
python3 03_organization/build_campaign_kb.py
python3 03_organization/build_sr3_lore_kb.py
python3 03_organization/build_sr3_topic_memory.py
```

Serving:
```bash
python3 05_serving/knowledge_wiki_server.py --port 8080
```

Legacy entrypoints in `scripts/` still work:
```bash
python3 scripts/build_campaign_kb.py
python3 scripts/knowledge_wiki_server.py
```
