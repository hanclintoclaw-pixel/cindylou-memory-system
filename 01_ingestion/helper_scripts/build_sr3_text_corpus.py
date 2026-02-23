#!/usr/bin/env python3
import argparse, os, json, glob, subprocess
from pathlib import Path
from pypdf import PdfReader

CATEGORIES = ["core_rules", "sourcebooks", "adventures", "player_aids"]


def find_pdfs(root: str):
    out = []
    for cat in CATEGORIES:
        cdir = os.path.join(root, cat)
        if not os.path.isdir(cdir):
            continue
        out.extend(sorted(glob.glob(os.path.join(cdir, "*.pdf"))))
    return out


def safe_name(path: str):
    return Path(path).stem


def preprocess(pdf: str, out_root: str, dpi: int = 300):
    from pdf_to_images import render_pdf
    book = safe_name(pdf)
    out = os.path.join(out_root, "images", book)
    return render_pdf(pdf, out, dpi)


def deepseek_ocr(image_dir: str, out_root: str):
    script = os.path.join(os.path.dirname(__file__), "ocr_with_deepseek.py")
    book = os.path.basename(image_dir)
    out = os.path.join(out_root, "ocr", book)
    cmd = [
        "python", script,
        "--images", os.path.join(image_dir, "*.png"),
        "--out", out,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def compile_texts(pdf: str, out_root: str):
    book = safe_name(pdf)
    ocr_dir = os.path.join(out_root, "ocr", book)
    comp_dir = os.path.join(out_root, "compiled")
    os.makedirs(comp_dir, exist_ok=True)
    target = os.path.join(comp_dir, f"{book}.txt")

    # preferred: OCR markdown outputs
    md_files = sorted(glob.glob(os.path.join(ocr_dir, "**", "*.md"), recursive=True))
    if md_files:
        with open(target, "w", encoding="utf-8") as w:
            for md in md_files:
                w.write(f"\n\n===== {os.path.basename(md)} =====\n")
                w.write(open(md, encoding="utf-8", errors="ignore").read())
        return {"book": book, "compiled": target, "source": "deepseek_markdown"}

    # fallback: pypdf extraction
    reader = PdfReader(pdf)
    with open(target, "w", encoding="utf-8") as w:
        for i, p in enumerate(reader.pages, start=1):
            txt = p.extract_text() or ""
            w.write(f"\n\n===== PAGE {i} =====\n{txt}")
    return {"book": book, "compiled": target, "source": "pypdf_fallback"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", required=True)
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--mode", choices=["preprocess", "deepseek", "compile", "all"], default="all")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    input_root = os.path.abspath(args.input_root)
    output_root = os.path.abspath(args.output_root)
    os.makedirs(output_root, exist_ok=True)

    pdfs = find_pdfs(input_root)
    report = {"mode": args.mode, "pdf_count": len(pdfs), "preprocess": [], "deepseek": [], "compile": [], "errors": []}

    for pdf in pdfs:
        try:
            if args.mode in ("preprocess", "all"):
                report["preprocess"].append(preprocess(pdf, output_root, args.dpi))

            if args.mode in ("deepseek", "all"):
                image_dir = os.path.join(output_root, "images", safe_name(pdf))
                if os.path.isdir(image_dir):
                    res = deepseek_ocr(image_dir, output_root)
                    report["deepseek"].append({"pdf": pdf, "code": res.returncode, "stdout": res.stdout[-5000:], "stderr": res.stderr[-5000:]})

            if args.mode in ("compile", "all"):
                report["compile"].append(compile_texts(pdf, output_root))

        except Exception as e:
            report["errors"].append({"pdf": pdf, "error": str(e)})

    out = os.path.join(output_root, "report.json")
    with open(out, "w", encoding="utf-8") as w:
        json.dump(report, w, indent=2)
    print(json.dumps({"ok": len(report["errors"]) == 0, "report": out, "errors": len(report["errors"])}, indent=2))


if __name__ == "__main__":
    main()
