#!/usr/bin/env python3
import argparse, os, json
import fitz  # pymupdf


def render_pdf(pdf_path: str, out_dir: str, dpi: int = 300):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pages = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out = os.path.join(out_dir, f"page_{i:04d}.png")
        pix.save(out)
        pages.append(out)
    return {"pdf": pdf_path, "pages": len(doc), "images": pages}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    result = render_pdf(args.pdf, args.out, args.dpi)
    print(json.dumps({"ok": True, **result}, indent=2))


if __name__ == "__main__":
    main()
