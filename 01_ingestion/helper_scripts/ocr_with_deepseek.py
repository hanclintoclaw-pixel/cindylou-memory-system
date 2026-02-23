#!/usr/bin/env python3
import argparse, os, json, glob


def load_model(model_name: str):
    from transformers import AutoModel, AutoTokenizer
    import torch
    tok = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name,
        _attn_implementation='flash_attention_2',
        trust_remote_code=True,
        use_safetensors=True,
    )
    model = model.eval().cuda().to(torch.bfloat16)
    return tok, model


def run_ocr(tokenizer, model, image_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    prompt = "<image>\\n<|grounding|>Convert the document to markdown."
    res = model.infer(
        tokenizer,
        prompt=prompt,
        image_file=image_path,
        output_path=out_dir,
        base_size=1024,
        image_size=768,
        crop_mode=True,
        save_results=True,
    )
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="Glob for page images")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="unsloth/DeepSeek-OCR-2")
    args = ap.parse_args()

    images = sorted(glob.glob(args.images))
    if not images:
        raise SystemExit("No images found")

    tokenizer, model = load_model(args.model)
    done = 0
    errors = []
    for img in images:
        stem = os.path.splitext(os.path.basename(img))[0]
        target = os.path.join(args.out, stem)
        try:
            run_ocr(tokenizer, model, img, target)
            done += 1
        except Exception as e:
            errors.append({"image": img, "error": str(e)})

    print(json.dumps({"ok": len(errors) == 0, "done": done, "errors": errors[:20]}, indent=2))


if __name__ == "__main__":
    main()
