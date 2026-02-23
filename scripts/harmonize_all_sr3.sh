#!/usr/bin/env bash
set -euo pipefail

WS="/Users/hanclaw/.openclaw/workspace-cindylou"
PY="python3"
HARMONIZER="$WS/scripts/harmonize_core_rulebook.py"
MAC_BASE="/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e/_ocr_remote/macos_vision"
DEEP_BASE="/Volumes/carbonite/GDrive/cindylou/Shadowrun_3e_Rules_Library/organized_3e/_ocr_remote/deepseek"
OUT_BASE="$WS/outputs/harmonized_all"
QUEUE_BASE="$WS/outputs/review_queue_all"

mkdir -p "$OUT_BASE" "$QUEUE_BASE"

for mac_dir in "$MAC_BASE"/*; do
  [[ -d "$mac_dir" ]] || continue
  name="$(basename "$mac_dir")"
  [[ "$name" == "_runner" || "$name" == "Icon" ]] && continue

  mac_file="$mac_dir/result.txt"
  [[ -f "$mac_file" ]] || continue

  deep_dir="$DEEP_BASE/$name"
  deep_file="$deep_dir/result.cleaned.md"

  out_dir="$OUT_BASE/$name"
  echo "[harmonize] $name"
  $PY "$HARMONIZER" \
    --mac-path "$mac_file" \
    --deepseek-path "$deep_file" \
    --output-dir "$out_dir" || true

  # Queue flagged items centrally for later human review
  review_jsonl="$out_dir/review_queue.jsonl"
  if [[ -f "$review_jsonl" ]]; then
    sed "s#^#{\"book\":\"$name\",\"item\":#; s#$#}#" "$review_jsonl" >> "$QUEUE_BASE/review_queue_all.jsonl" || true
  fi
done

echo "done: harmonization sweep complete"
