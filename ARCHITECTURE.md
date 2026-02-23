# Staged Pipeline Architecture

This repository is organized as a staged data pipeline:

## 01_ingestion
Purpose: Pull raw external content and run OCR collection runners.

Inputs
- `RAW_ROOT` datasets (Game Logs, SR3 OCR source tree)

Outputs
- Imported markdown under `MEMORY_ROOT`
- OCR batch outputs under `_ocr_remote` source tree

Key scripts
- `01_ingestion/ingest_wordpress_gdocs.py`
- `01_ingestion/sr3_macos_ocr_runner.sh`
- `01_ingestion/sr3_deepseek_ocr_runner.sh`
- `01_ingestion/helper_scripts/*`

## 02_cleanup
Purpose: Harmonize/clean OCR outputs and create review queues.

Inputs
- OCR results from `_ocr_remote/macos_vision` + `_ocr_remote/deepseek`

Outputs
- Harmonized markdown and metadata in `INTERMEDIATES_ROOT/outputs/harmonized_all`
- Consolidated review queue in `INTERMEDIATES_ROOT/outputs/review_queue_all`

Key scripts
- `02_cleanup/harmonize_core_rulebook.py`
- `02_cleanup/harmonize_all_sr3.sh`

## 03_organization
Purpose: Build topic/lore/campaign knowledge artifacts and process request queues.

Inputs
- Harmonized OCR outputs
- Campaign logs and imported wordpress content

Outputs
- Structured memory docs and indexes under `MEMORY_ROOT`

Key scripts
- `03_organization/build_sr3_topic_memory.py`
- `03_organization/build_sr3_lore_kb.py`
- `03_organization/build_campaign_kb.py`
- `03_organization/process_entity_queue.py`

## 04_caching
Purpose: Reserved stage for cache materialization/index databases.

Inputs/Outputs
- Cache artifacts rooted at `CACHE_ROOT`

## 05_serving
Purpose: Serve searchable wiki/UI over organized memory artifacts.

Inputs
- `MEMORY_ROOT` outputs from organization stage

Outputs
- HTTP server process for interactive browsing and queue intake

Key script
- `05_serving/knowledge_wiki_server.py`

## Shared Configuration
Path configuration is centralized via:
- `.env.example` (copy to `.env` for local overrides)
- `config/pipeline_paths.py`

Canonical defaults:
- `CODE_ROOT=/Users/hanclaw/claw/projects/cindylou`
- `RAW_ROOT=/Volumes/carbonite/GDrive/cindylou`
- `DATA_ROOT=/Volumes/carbonite/claw/data/cindylou`
- `CLEANED_ROOT=/Volumes/carbonite/claw/data/cindylou/cleaned`
- `INTERMEDIATES_ROOT=/Volumes/carbonite/claw/data/cindylou/intermediates`
- `CACHE_ROOT=/Volumes/carbonite/claw/data/cindylou/cache`

Derived defaults:
- `MEMORY_ROOT=$DATA_ROOT/memory`
- `OUTPUTS_ROOT=$INTERMEDIATES_ROOT/outputs`
