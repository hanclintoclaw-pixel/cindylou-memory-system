#!/usr/bin/env python3
import json
import subprocess
import time
from pathlib import Path
import fitz

ROOT = Path('/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e')
OUT = ROOT / '_ocr_remote' / 'macos_vision'
SWIFT = ROOT / 'helper_scripts' / 'vision_ocr_image.swift'
PDF_DIRS = ['core_rules', 'sourcebooks', 'adventures', 'player_aids']


def list_pdfs():
    files = []
    for d in PDF_DIRS:
        for f in sorted((ROOT / d).glob('*.pdf')):
            if f.name.startswith('._') or f.name.startswith('.'):
                continue
            files.append(f)
    return files


def render_page(pdf_path: Path, page_idx: int, png_path: Path, dpi=220):
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(png_path))
    doc.close()


def ocr_image(img_path: Path):
    cp = subprocess.run(['swift', str(SWIFT), str(img_path)], capture_output=True, text=True, timeout=120)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or f'code {cp.returncode}')
    return cp.stdout


def process_pdf(pdf: Path):
    rel = pdf.relative_to(ROOT)
    stem = str(rel).replace('/', '__').replace('.pdf', '')
    out_dir = OUT / stem
    images = out_dir / 'images'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_txt = out_dir / 'result.txt'
    meta = out_dir / 'meta.json'

    if out_txt.exists() and out_txt.stat().st_size > 100:
        return {'pdf': str(rel), 'status': 'skipped_existing'}

    doc = fitz.open(pdf)
    total = len(doc)
    doc.close()
    chunks = []
    failed = []
    t0 = time.time()

    for i in range(total):
        page_no = i + 1
        png = images / f'page_{page_no:04d}.png'
        try:
            if not png.exists():
                render_page(pdf, i, png)
            txt = ocr_image(png)
            chunks.append(f"\n\n===== PAGE {page_no} =====\n{txt}")
        except Exception as e:
            failed.append({'page': page_no, 'error': str(e)})
            chunks.append(f"\n\n===== PAGE {page_no} =====\n[OCR_ERROR] {e}")

    merged = ''.join(chunks)
    out_txt.write_text(merged, encoding='utf-8')
    m = {
        'pdf': str(rel),
        'status': 'ok' if not failed else 'partial',
        'pages': total,
        'failed_pages': len(failed),
        'duration_sec': round(time.time()-t0, 2),
    }
    if failed:
        m['errors'] = failed[:50]
    meta.write_text(json.dumps(m, indent=2), encoding='utf-8')
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = list_pdfs()
    summary = {'total': len(pdfs), 'ok': 0, 'partial': 0, 'skipped_existing': 0, 'error': 0, 'items': []}
    for i,p in enumerate(pdfs,1):
        print(f'[{i}/{len(pdfs)}] {p.name}', flush=True)
        try:
            r = process_pdf(p)
        except Exception as e:
            r = {'pdf': str(p.relative_to(ROOT)), 'status': 'error', 'error': str(e)}
        summary['items'].append(r)
        summary[r['status']] = summary.get(r['status'],0)+1
        (OUT/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
