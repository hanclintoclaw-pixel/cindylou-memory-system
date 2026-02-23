# SR3 OCR Helper Scripts

These scripts live next to the organized 3E data and are designed to build a high-quality OCR corpus.

## Important platform note

`unsloth/DeepSeek-OCR-2` currently targets **CUDA/NVIDIA** inference (flash-attn path).
On Apple Silicon macOS, you can still run extraction + page rendering locally, but DeepSeek-OCR-2 acceleration is not a native fit today.

So this folder supports 2 tracks:

1. **Local preprocessing on Mac** (PDF -> page images / metadata)
2. **DeepSeek OCR on CUDA box** (same scripts + model backend)

## Files

- `requirements.txt` - base deps for PDF parsing/rendering
- `requirements_deepseek_cuda.txt` - optional CUDA inference deps
- `pdf_to_images.py` - render each PDF page to PNG
- `ocr_with_deepseek.py` - run DeepSeek-OCR-2 over page images
- `build_sr3_text_corpus.py` - orchestrate extraction pipeline

## Quick start (macOS preprocessing)

```bash
cd "/Volumes/carbonite/GDrive/cindylou/Shadowrun 3e Rules Library/organized_3e/helper_scripts"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python build_sr3_text_corpus.py \
  --input-root .. \
  --output-root ../_ocr_work \
  --mode preprocess
```

## Quick start (CUDA DeepSeek OCR)

On a Linux/NVIDIA machine:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_deepseek_cuda.txt

python build_sr3_text_corpus.py \
  --input-root .. \
  --output-root ../_ocr_work \
  --mode deepseek
```

## Output layout

`_ocr_work/` contains:
- `images/<book>/<page>.png`
- `ocr/<book>/<page>.md`
- `compiled/<book>.txt` (page-marked merged output)
- `report.json` (coverage + failures)

## SR3-only policy

Use these scripts only for SR3 corpus maintenance. Keep edition provenance in `../manifest.json`.
