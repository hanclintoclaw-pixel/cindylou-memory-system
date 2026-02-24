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
python3 03_organization/build_entity_manifest.py
python3 03_organization/build_campaign_intro_timeline.py
```

Serving:
```bash
python3 05_serving/knowledge_wiki_server.py --port 8080
python3 05_serving/memory_api_server.py --port 8091
```

CLI bridge:
```bash
python3 cindylou.py search --type keyword --q "otaku" --scope sr3_rules
python3 cindylou.py search --type semantic --q "who rescued cindy lou" --scope campaign
python3 cindylou.py get campaign/entities/mevin.md
python3 cindylou.py upsert-fact --json '{"entity":"Mevin Kitnick","fact":"Rescued Cindy Lou from obsessed fans"}'
python3 cindylou.py restart --service all
```

API bridge:
```bash
curl -s http://127.0.0.1:8091/health
curl -s -X POST http://127.0.0.1:8091/search -H 'content-type: application/json' -d '{"query":"semi-autonomous knowbot","mode":"keyword","scope":"sr3_rules"}'
curl -s -X POST http://127.0.0.1:8091/facts -H 'content-type: application/json' -d '{"entity":"Mevin Kitnick","fact":"Rescued Cindy Lou"}'
```

Legacy entrypoints in `scripts/` still work:
```bash
python3 scripts/build_campaign_kb.py
python3 scripts/knowledge_wiki_server.py
```
