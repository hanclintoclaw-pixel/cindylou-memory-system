#!/usr/bin/env python3
import json
import re
import urllib.request
from pathlib import Path

WS = Path('/Users/hanclaw/.openclaw/workspace-cindylou')
SRC = Path('/Volumes/carbonite/GDrive/cindylou/Game_Logs/Historical Wordpress Posts')
OUT = WS / 'memory' / 'wordpress_ingest'
OUT.mkdir(parents=True, exist_ok=True)


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-')


def export_doc(doc_id: str) -> str:
    url = f'https://docs.google.com/document/d/{doc_id}/export?format=txt'
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read().decode('utf-8', errors='replace')


def main():
    count = 0
    for folder in sorted([p for p in SRC.iterdir() if p.is_dir()]):
        out_dir = OUT / folder.name
        out_dir.mkdir(parents=True, exist_ok=True)
        for g in sorted(folder.glob('*.gdoc')):
            try:
                meta = json.loads(g.read_text(encoding='utf-8', errors='replace'))
                doc_id = meta.get('doc_id')
                if not doc_id:
                    continue
                text = export_doc(doc_id)
                if not text.strip():
                    continue
                out = out_dir / (slugify(g.stem) + '.md')
                out.write_text(
                    f"# Imported: {g.stem}\n\n"
                    f"- Source gdoc: `{g}`\n"
                    f"- Doc ID: `{doc_id}`\n\n"
                    + text.strip() + '\n',
                    encoding='utf-8',
                )
                count += 1
            except Exception:
                continue
    print('imported', count)


if __name__ == '__main__':
    main()
