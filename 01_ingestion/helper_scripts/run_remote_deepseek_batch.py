#!/usr/bin/env python3
import json
import subprocess
import time
from pathlib import Path

import fitz
from clean_deepseek_markdown import clean_text

ROOT = Path('/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e')
OUT = ROOT / '_ocr_remote' / 'deepseek'
PROMPT = '<image>\n<|grounding|>Convert the document to markdown.'
ENDPOINT = 'http://10.0.1.134:8000/ocr'
PDF_DIRS = ['core_rules', 'sourcebooks', 'adventures', 'player_aids']
DPI = 180
PER_PAGE_TIMEOUT_SEC = 180
RETRIES = 3


def list_pdfs():
    files = []
    for d in PDF_DIRS:
        p = ROOT / d
        if p.exists():
            for f in sorted(p.glob('*.pdf')):
                if f.name.startswith('._') or f.name.startswith('.'):
                    continue
                files.append(f)
    return files


def render_page(doc, page_idx: int, png_path: Path, dpi=DPI):
    page = doc[page_idx]
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(png_path))


def ocr_png(png_path: Path):
    cmd = [
        'curl', '-sS', '-f', '--max-time', str(PER_PAGE_TIMEOUT_SEC), ENDPOINT,
        '-F', f'file=@{png_path}',
        '--form-string', f'prompt={PROMPT}',
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        return None, (cp.stderr.strip() or f'returncode={cp.returncode}')
    body = cp.stdout.strip()
    if not body:
        return None, 'empty response body'
    try:
        parsed = json.loads(body)
        result_text = parsed.get('result', '')
        if not isinstance(result_text, str):
            result_text = json.dumps(result_text, ensure_ascii=False, indent=2)
        return result_text, None
    except Exception as e:
        return None, f'json parse error: {e}'


def process_pdf(pdf: Path):
    rel = pdf.relative_to(ROOT)
    stem = str(rel).replace('/', '__').replace('.pdf', '')
    out_dir = OUT / stem
    images = out_dir / 'images'
    pages_dir = out_dir / 'pages'
    pages_dir.mkdir(parents=True, exist_ok=True)

    out_md = out_dir / 'result.md'
    cleaned_md = out_dir / 'result.cleaned.md'
    meta_json = out_dir / 'meta.json'

    doc = fitz.open(pdf)
    total_pages = len(doc)

    failed = []
    chars = 0
    t0 = time.time()

    for i in range(total_pages):
        page_no = i + 1
        png = images / f'page_{page_no:04d}.png'
        page_md = pages_dir / f'page_{page_no:04d}.md'

        if page_md.exists() and page_md.stat().st_size > 10:
            chars += page_md.stat().st_size
            continue

        try:
            if not png.exists():
                render_page(doc, i, png)

            last_err = None
            text = None
            for attempt in range(1, RETRIES + 1):
                text, err = ocr_png(png)
                if text is not None:
                    break
                last_err = err
                time.sleep(min(6, attempt * 2))

            if text is None:
                raise RuntimeError(last_err or 'unknown OCR error')

            page_md.write_text(text, encoding='utf-8')
            chars += len(text)

        except Exception as e:
            failed.append({'page': page_no, 'error': str(e)})
            page_md.write_text(f'[OCR_ERROR] {e}\n', encoding='utf-8')

    doc.close()

    merged = []
    for i in range(1, total_pages + 1):
        page_md = pages_dir / f'page_{i:04d}.md'
        txt = page_md.read_text(encoding='utf-8') if page_md.exists() else '[MISSING_PAGE_OUTPUT]'
        merged.append(f'\n\n===== PAGE {i} =====\n{txt}')

    merged_text = ''.join(merged)
    out_md.write_text(merged_text, encoding='utf-8')
    cleaned_md.write_text(clean_text(merged_text), encoding='utf-8')

    status = 'ok' if not failed else ('partial' if len(failed) < total_pages else 'error')
    meta = {
        'pdf': str(rel),
        'status': status,
        'pages': total_pages,
        'failed_pages': len(failed),
        'duration_sec': round(time.time() - t0, 2),
        'chars': chars,
        'cleaned_chars': cleaned_md.stat().st_size if cleaned_md.exists() else 0,
        'endpoint': ENDPOINT,
        'prompt': PROMPT,
    }
    if failed:
        meta['errors'] = failed[:200]
    meta_json.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = list_pdfs()
    summary = {
        'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'endpoint': ENDPOINT,
        'mode': 'png_per_page',
        'total': len(pdfs),
        'ok': 0,
        'partial': 0,
        'skipped_existing': 0,
        'error': 0,
        'items': []
    }

    for i, pdf in enumerate(pdfs, start=1):
        print(f'[{i}/{len(pdfs)}] {pdf.name}', flush=True)
        rel = str(pdf.relative_to(ROOT))
        out_dir = OUT / rel.replace('/', '__').replace('.pdf', '')
        out_md = out_dir / 'result.md'
        if out_md.exists() and out_md.stat().st_size > 100:
            r = {'pdf': rel, 'status': 'skipped_existing'}
        else:
            try:
                r = process_pdf(pdf)
            except Exception as e:
                r = {'pdf': rel, 'status': 'error', 'error': str(e)}
        summary['items'].append(r)
        summary[r['status']] = summary.get(r['status'], 0) + 1
        (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    summary['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['total', 'ok', 'partial', 'skipped_existing', 'error']}, indent=2))


if __name__ == '__main__':
    main()
