#!/usr/bin/env python3
"""Shared path configuration for staged CindyLou pipeline scripts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"

DEFAULTS = {
    "CODE_ROOT": "/Users/hanclaw/claw/projects/cindylou",
    "RAW_ROOT": "/Volumes/carbonite/GDrive/cindylou",
    "DATA_ROOT": "/Volumes/carbonite/claw/data/cindylou",
    "CLEANED_ROOT": "/Volumes/carbonite/claw/data/cindylou/cleaned",
    "INTERMEDIATES_ROOT": "/Volumes/carbonite/claw/data/cindylou/intermediates",
    "CACHE_ROOT": "/Volumes/carbonite/claw/data/cindylou/cache",
}


def _load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


@dataclass(frozen=True)
class PipelinePaths:
    code_root: Path
    raw_root: Path
    data_root: Path
    cleaned_root: Path
    intermediates_root: Path
    cache_root: Path
    repo_root: Path
    memory_root: Path
    outputs_root: Path


def get_paths() -> PipelinePaths:
    _load_dotenv()

    def pick(name: str) -> Path:
        return Path(os.environ.get(name, DEFAULTS[name]))

    code_root = pick("CODE_ROOT")
    raw_root = pick("RAW_ROOT")
    data_root = pick("DATA_ROOT")
    cleaned_root = pick("CLEANED_ROOT")
    intermediates_root = pick("INTERMEDIATES_ROOT")
    cache_root = pick("CACHE_ROOT")

    memory_root = Path(os.environ.get("MEMORY_ROOT", str(data_root / "memory")))
    outputs_root = Path(os.environ.get("OUTPUTS_ROOT", str(intermediates_root / "outputs")))

    return PipelinePaths(
        code_root=code_root,
        raw_root=raw_root,
        data_root=data_root,
        cleaned_root=cleaned_root,
        intermediates_root=intermediates_root,
        cache_root=cache_root,
        repo_root=REPO_ROOT,
        memory_root=memory_root,
        outputs_root=outputs_root,
    )
