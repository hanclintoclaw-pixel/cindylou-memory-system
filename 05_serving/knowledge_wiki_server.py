#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    import markdown
except Exception as e:
    raise RuntimeError(
        "Missing dependency 'markdown'. Install with: python3 -m pip install markdown"
    ) from e

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.pipeline_paths import get_paths

P = get_paths()
WS = P.repo_root
MEMORY_ROOT = Path(os.environ.get('MEMORY_ROOT', str(P.cleaned_root / 'memory')))
CONSOLIDATED_ROOT = MEMORY_ROOT / '10_consolidated'
MANIFEST_PATH = CONSOLIDATED_ROOT / 'entity_manifest.jsonl'
CAMPAIGN_TIMELINE_PATH = MEMORY_ROOT / '90_derived' / 'CAMPAIGN_INTRO_TIMELINE.md'
QUEUE_FILE = MEMORY_ROOT / 'entity_request_queue.jsonl'
PLAYER_INPUT_FILE = MEMORY_ROOT / 'player_input' / 'submissions.jsonl'
DEBUG_SOURCE_ROOTS = [MEMORY_ROOT, P.raw_root, P.cleaned_root, P.data_root]
WIKI_PASSWORD = os.environ.get('WIKI_PASSWORD', 'neilbreen')
SESSION_COOKIE = 'cindywiki_session'
SESSION_TTL_SEC = 60 * 60 * 24 * 7
SESSIONS: dict[str, int] = {}


@dataclass
class Article:
    slug: str
    title: str
    path: Path | None
    body: str
    category: str  # general|campaign|core


def load_markdown(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def heading_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('#'):
            return s.lstrip('#').strip() or fallback
    return fallback


def read_queue():
    if not QUEUE_FILE.exists():
        return []
    rows = []
    for line in QUEUE_FILE.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def append_queue(entity: str, note: str = ''):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    obj = {
        'ts': now,
        'created_at': now,
        'updated_at': now,
        'entity': entity.strip(),
        'note': note.strip(),
        'status': 'incoming',
        'history': [
            {'ts': now, 'event': 'incoming', 'detail': 'added via web queue'}
        ],
    }
    with QUEUE_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def read_player_input():
    if not PLAYER_INPUT_FILE.exists():
        return []
    rows = []
    for line in PLAYER_INPUT_FILE.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def safe_source_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    raw = unquote(path_value).strip()
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    for root in DEBUG_SOURCE_ROOTS:
        try:
            p.relative_to(root.resolve())
            return p
        except Exception:
            continue
    return None


def append_player_input(entity: str, player: str, note: str, request_type: str = 'fact'):
    PLAYER_INPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        'ts': int(time.time()),
        'date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'entity': entity.strip(),
        'player': player.strip() or 'Unknown Player',
        'request_type': request_type.strip() or 'fact',
        'note': note.strip(),
        'status': 'new',
    }
    with PLAYER_INPUT_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def list_entity_choices(articles: dict[str, Article]):
    names = []
    for slug, a in articles.items():
        if slug.startswith('campaign-entities-'):
            names.append(a.title.replace('Campaign NPC: ', '').replace('Campaign PC: ', '').replace('Campaign Entity: ', '').strip())
    return sorted(set(n for n in names if n))


def load_manifest_rows():
    rows = []
    if not MANIFEST_PATH.exists():
        return rows
    for line in MANIFEST_PATH.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def aggregate_entity_markdown(md_paths: list[Path]) -> str:
    parts = []
    for mp in sorted(md_paths, key=lambda x: x.name.lower()):
        if mp.exists():
            parts.append(load_markdown(mp).strip())
    return '\n\n'.join(p for p in parts if p).strip()


def build_articles() -> dict[str, Article]:
    articles: dict[str, Article] = {}

    cindy_parts = []
    for p in [WS / 'CHARACTER_PROFILE.md', WS / 'IDENTITY.md', WS / 'SOUL.md']:
        if p.exists():
            cindy_parts.append(load_markdown(p))
    cindy_body = '\n\n'.join(cindy_parts).strip() or '# Cindy Lou Jenkins\n\nNo profile found yet.'
    articles['cindy-lou-jenkins'] = Article('cindy-lou-jenkins', 'Cindy Lou Jenkins', None, cindy_body, 'core')

    manifest_rows = load_manifest_rows()
    if manifest_rows:
        for row in manifest_rows:
            entity = row.get('entity', '').strip()
            scope = row.get('scope', '').strip().lower()
            md_files = [Path(x) for x in row.get('md_files', []) if str(x).strip()]
            jsonl_files = [Path(x) for x in row.get('jsonl_files', []) if str(x).strip()]
            if not entity or not md_files:
                continue
            slug_base = entity.replace('_', '-').lower()
            if scope == 'campaign':
                slug = f'campaign-entities-{slug_base}'
                category = 'campaign'
            else:
                slug = f'lore-entities-{slug_base}'
                category = 'general'

            body = aggregate_entity_markdown(md_files)
            if jsonl_files:
                body += '\n\n## Data files (JSONL)\n'
                for jf in sorted(jsonl_files, key=lambda x: x.name.lower()):
                    body += f"\n- `{jf.name}`"
            title = heading_title(body, entity.replace('-', ' ').title())
            articles[slug] = Article(slug, title, md_files[0], body, category)
    else:
        for root, slug_prefix, category in [
            (CONSOLIDATED_ROOT / 'general' / 'entities', 'lore-entities', 'general'),
            (CONSOLIDATED_ROOT / 'campaign' / 'entities', 'campaign-entities', 'campaign'),
        ]:
            if not root.exists():
                continue
            groups = {}
            for md in root.glob('*.md'):
                base = md.stem.split('.', 1)[0]
                groups.setdefault(base, []).append(md)
            for base, md_paths in groups.items():
                slug = f"{slug_prefix}-{base.replace('_', '-').lower()}"
                body = aggregate_entity_markdown(md_paths)
                title = heading_title(body, base.replace('-', ' ').title())
                articles[slug] = Article(slug, title, md_paths[0], body, category)

    # Back-compat merge: also scan legacy lore/campaign trees so older data doesn't disappear.
    for root, slug_prefix, category in [
        (MEMORY_ROOT / 'lore', 'lore', 'general'),
        (MEMORY_ROOT / 'campaign' / 'entities', 'campaign-entities', 'campaign'),
        (MEMORY_ROOT / 'campaign', 'campaign', 'campaign'),
    ]:
        if not root.exists():
            continue
        for md in sorted(root.rglob('*.md')):
            # Avoid duplicating request docs and nested entity duplicates handled elsewhere
            if 'requests' in md.parts:
                continue
            if root == (MEMORY_ROOT / 'campaign') and 'entities' in md.parts:
                continue
            rel = md.relative_to(root)
            slug = f"{slug_prefix}-" + '-'.join(rel.with_suffix('').parts).lower().replace('_', '-')
            if slug in articles:
                continue
            text_md = load_markdown(md)
            title = heading_title(text_md, rel.stem.replace('_', ' ').title())
            articles[slug] = Article(slug, title, md, text_md, category)

    for root, slug_prefix, category in [
        (MEMORY_ROOT / 'topics', 'topics', 'general'),
        (CONSOLIDATED_ROOT / 'sessions', 'sessions', 'campaign'),
    ]:
        if not root.exists():
            continue
        for md in sorted(root.rglob('*.md')):
            rel = md.relative_to(root)
            slug = f"{slug_prefix}-" + '-'.join(rel.with_suffix('').parts).lower().replace('_', '-')
            text_md = load_markdown(md)
            title = heading_title(text_md, rel.stem.replace('_', ' ').title())
            articles[slug] = Article(slug, title, md, text_md, category)

    requests_root = MEMORY_ROOT / 'campaign' / 'requests'
    if requests_root.exists():
        for md in sorted(requests_root.glob('*.md')):
            slug = 'campaign-requests-' + md.stem.replace('_', '-').lower()
            text_md = load_markdown(md)
            title = heading_title(text_md, md.stem.replace('_', ' ').title())
            articles[slug] = Article(slug, title, md, text_md, 'campaign-queue')

    articles['index'] = Article('index', 'Index', None, '# Index\n\nBrowse every knowledge article.', 'core')
    articles['entity-queue'] = Article('entity-queue', 'Entity Request Queue', None, '# Entity Request Queue', 'core')
    return articles


def compile_linker(articles: dict[str, Article]):
    name_to_slug = {}
    for slug, a in articles.items():
        if slug in {'index', 'entity-queue'}:
            continue
        name_to_slug[a.title] = slug

        for line in a.body.splitlines():
            s = line.strip()
            if not s.lower().startswith('- synonyms:'):
                continue
            raw = s.split(':', 1)[1].strip()
            if not raw or raw.lower() == '_none_':
                continue
            for alias in [x.strip() for x in raw.split(',')]:
                if alias:
                    name_to_slug[alias] = slug

    for slug in articles:
        if slug.startswith('lore-entities-') or slug.startswith('campaign-entities-'):
            alias = slug.split('-', 2)[-1].replace('-', ' ')
            if alias:
                name_to_slug[alias.title()] = slug

    names = sorted(name_to_slug.keys(), key=len, reverse=True)
    if not names:
        return None, name_to_slug
    pattern = re.compile(r'(?<![\w/])(' + '|'.join(re.escape(n) for n in names) + r')(?![\w/])')
    return pattern, name_to_slug


def markdown_to_html(md_text: str) -> str:
    return markdown.markdown(
        md_text,
        extensions=[
            'extra',
            'sane_lists',
            'tables',
            'toc',
            'nl2br',
        ],
        output_format='html5',
    )


def autolink_html(html_text: str, current_slug: str, pattern, name_to_slug):
    if not pattern:
        return html_text, set()
    refs = set()

    def repl(m):
        name = m.group(1)
        target = name_to_slug.get(name)
        if not target or target == current_slug:
            return name
        refs.add(target)
        return f'<a href="/article/{quote(target)}">{html.escape(name)}</a>'

    chunks = re.split(r'(<[^>]+>)', html_text)
    for i, c in enumerate(chunks):
        if c.startswith('<') and c.endswith('>'):
            continue
        chunks[i] = pattern.sub(repl, c)
    return ''.join(chunks), refs


def render_login(error: str = ''):
    err = f"<p style='color:#b00020'>{html.escape(error)}</p>" if error else ''
    return f"""<!doctype html><html><head><meta charset=\"utf-8\" /><title>Cindy Wiki Login</title>
<style>body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 460px; margin: 4rem auto; padding: 0 1rem; }}
.card {{ border:1px solid #ddd; border-radius:10px; padding:1rem; }} input {{ width:100%; padding:.55rem; margin:.4rem 0 .8rem 0; }} button {{ padding:.5rem .8rem; }}</style>
</head><body><div class='card'><h2>Cindy Knowledge Wiki</h2><p>Password required.</p>{err}
<form method='POST' action='/login'><input type='password' name='password' placeholder='Password' autofocus required />
<button type='submit'>Unlock</button></form></div></body></html>"""


def render_page(title: str, body_html: str):
    return f"""<!doctype html><html><head><meta charset=\"utf-8\" />
<title>{html.escape(title)} - Cindy Knowledge Wiki</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 1040px; margin: 2rem auto; padding: 0 1rem; line-height: 1.45; }}
a {{ color:#0b57d0; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.header {{ display:flex; justify-content:space-between; gap:1rem; align-items:center; margin-bottom:1rem; }}
.nav a {{ margin-right:.8rem; }} .card {{ border:1px solid #ddd; border-radius:10px; padding:.9rem 1rem; margin:.7rem 0; }}
.meta {{ color:#555; font-size:.93rem; margin-bottom:.7rem; }}
code {{ background:#f5f5f5; padding:0 .2rem; border-radius:4px; }}
pre {{ background:#111; color:#eaeaea; padding:.8rem; border-radius:8px; overflow:auto; }}
.mermaid {{ background:#fff; border:1px solid #ddd; border-radius:8px; padding:.75rem; overflow:auto; }}
input, textarea {{ width:100%; padding:.5rem; margin:.25rem 0 .6rem 0; }}
button {{ padding:.5rem .75rem; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head><body>
<div class=\"header\"><div><strong>Cindy Lou Jenkins — Knowledge Wiki</strong></div>
<div class=\"nav\"><a href=\"/\">Front Page</a><a href=\"/article/index\">Index</a><a href=\"/article/campaign-timeline\">Campaign Timeline</a><a href=\"/article/data-diagnostics\">Data Diagnostics</a><a href=\"/article/entity-queue\">Entity Queue</a></div></div>
{body_html}
<script>
(() => {{
  const blocks = document.querySelectorAll('pre > code.language-mermaid, pre > code.lang-mermaid');
  if (!blocks.length) return;
  blocks.forEach((codeEl) => {{
    const pre = codeEl.parentElement;
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = codeEl.textContent || '';
    pre.replaceWith(div);
  }});
  if (window.mermaid) {{
    mermaid.initialize({{ startOnLoad: false, securityLevel: 'loose', theme: 'default' }});
    mermaid.run({{ querySelector: '.mermaid' }});
  }}
}})();
</script>
</body></html>"""


class WikiHandler(BaseHTTPRequestHandler):
    def get_session_token(self):
        raw = self.headers.get('Cookie', '')
        for part in raw.split(';'):
            p = part.strip()
            if p.startswith(SESSION_COOKIE + '='):
                return p.split('=', 1)[1]
        return None

    def is_authenticated(self):
        token = self.get_session_token()
        if not token:
            return False
        exp = SESSIONS.get(token)
        if not exp:
            return False
        if exp < int(time.time()):
            SESSIONS.pop(token, None)
            return False
        return True

    def require_auth_or_login(self):
        if self.is_authenticated():
            return True
        self.respond_html(render_login())
        return False

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length).decode('utf-8', errors='replace')
        form = parse_qs(body)

        if parsed.path == '/login':
            pw = (form.get('password', [''])[0] or '')
            if hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(WIKI_PASSWORD.encode()).hexdigest():
                token = secrets.token_urlsafe(24)
                SESSIONS[token] = int(time.time()) + SESSION_TTL_SEC
                self.send_response(303)
                self.send_header('Set-Cookie', f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax")
                self.send_header('Location', '/')
                self.end_headers()
            else:
                self.respond_html(render_login('Invalid password.'))
            return

        if not self.is_authenticated():
            self.respond_html(render_login())
            return

        if parsed.path == '/queue-add':
            entity = (form.get('entity', [''])[0] or '').strip()
            note = (form.get('note', [''])[0] or '').strip()
            if entity:
                append_queue(entity, note)
            self.send_response(303)
            self.send_header('Location', '/article/entity-queue')
            self.end_headers()
            return

        if parsed.path == '/player-input-add':
            entity = (form.get('entity', [''])[0] or '').strip()
            player = (form.get('player', [''])[0] or '').strip()
            note = (form.get('note', [''])[0] or '').strip()
            request_type = (form.get('request_type', ['fact'])[0] or 'fact').strip()
            target_slug = (form.get('target_slug', [''])[0] or '').strip()
            if entity and note:
                append_player_input(entity, player, note, request_type)
                if request_type in {'research', 'update', 'question'}:
                    append_queue(entity, f"[{player or 'Unknown Player'}] {note}")
            redirect = f"/article/{target_slug}" if target_slug else '/article/entity-queue'
            self.send_response(303)
            self.send_header('Location', redirect)
            self.end_headers()
            return

        self.send_error(404, 'Not found')

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/login':
            self.respond_html(render_login())
            return

        if not self.require_auth_or_login():
            return

        articles = build_articles()
        pattern, name_to_slug = compile_linker(articles)

        outgoing = {}
        for slug, a in articles.items():
            if slug in {'index', 'entity-queue'}:
                continue
            raw_html = markdown_to_html(a.body)
            _, refs = autolink_html(raw_html, slug, pattern, name_to_slug)
            outgoing[slug] = refs

        inbound_count = {slug: 0 for slug in articles}
        inbound_sources = {slug: [] for slug in articles}
        for src, tgts in outgoing.items():
            for t in tgts:
                if t in inbound_count:
                    inbound_count[t] += 1
                    inbound_sources[t].append(src)

        if path == '/':
            self.serve_article(articles, inbound_count, inbound_sources, pattern, name_to_slug, 'cindy-lou-jenkins')
            return
        if path == '/article/index':
            self.serve_index(articles, inbound_count)
            return
        if path == '/article/campaign-timeline':
            self.serve_campaign_timeline()
            return
        if path == '/article/data-diagnostics':
            self.serve_data_diagnostics(articles)
            return
        if path == '/debug/source':
            self.serve_source_debug(parsed)
            return
        if path == '/article/entity-queue':
            self.serve_queue(articles, inbound_count, pattern, name_to_slug)
            return
        if path.startswith('/article/'):
            self.serve_article(articles, inbound_count, inbound_sources, pattern, name_to_slug, path[len('/article/'):])
            return

        self.send_error(404, 'Not found')

    def serve_index(self, articles, inbound_count):
        cards = ['<h1>Index</h1>', '<p>Every article in the knowledgebase.</p>']
        cats = {}
        for slug, a in articles.items():
            cats.setdefault(a.category, []).append((slug, a))
        for cat in ['core', 'general', 'campaign', 'campaign-queue']:
            if cat not in cats:
                continue
            cards.append(f'<h2>{html.escape(cat.replace('-', ' ').title())}</h2><div class="card"><ul>')
            for slug, a in sorted(cats[cat], key=lambda x: x[1].title.lower()):
                cards.append(
                    f'<li><a href="/article/{quote(slug)}">{html.escape(a.title)}</a> '
                    f'<span class="meta">(referenced by {inbound_count.get(slug,0)} items)</span></li>'
                )
            cards.append('</ul></div>')
        self.respond_html(render_page('Index', '\n'.join(cards)))

    def serve_queue(self, articles, inbound_count, pattern, name_to_slug):
        rows = read_queue()
        choices = list_entity_choices(articles)
        options = ''.join(f"<option value='{html.escape(c)}'>{html.escape(c)}</option>" for c in choices)
        body = [
            '<h1>Entity Request Queue</h1>',
            '<p>Request a new named entity, or submit additional facts/requests for an existing one.</p>',
            '<div class="card"><form method="POST" action="/queue-add">'
            '<label>Entity name (new or existing)</label><input name="entity" list="entities" placeholder="e.g., Otaku or Harac" required />'
            f"<datalist id='entities'>{options}</datalist>"
            '<label>Note (optional)</label><textarea name="note" rows="3" placeholder="Why this matters"></textarea>'
            '<button type="submit">Add to queue</button></form></div>',
            '<div class="card"><h3>Player Input</h3>'
            '<form method="POST" action="/player-input-add">'
            '<input type="hidden" name="target_slug" value="entity-queue" />'
            '<label>Player name</label><input name="player" placeholder="Your name" />'
            '<label>Entity</label><input name="entity" list="entities" placeholder="Existing entity or new one" required />'
            '<label>Request type</label><select name="request_type"><option value="fact">Fact</option><option value="update">Update</option><option value="research">Research request</option><option value="question">Question</option></select>'
            '<label>Submission</label><textarea name="note" rows="4" placeholder="Add facts, corrections, or requests"></textarea>'
            '<button type="submit">Submit player input</button></form></div>',
            '<h2>Queued entities</h2><div class="card"><ul>'
        ]
        for r in sorted(rows, key=lambda x: x.get('ts', 0), reverse=True):
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r.get('ts', 0)))
            body.append(f"<li><strong>{html.escape(r.get('entity',''))}</strong> <span class='meta'>[{html.escape(r.get('status','pending'))}] {ts}</span>")
            if r.get('note'):
                body.append(f"<div class='meta'>{html.escape(r.get('note'))}</div>")
            body.append('</li>')
        body.append('</ul></div>')
        self.respond_html(render_page('Entity Queue', '\n'.join(body)))

    def serve_campaign_timeline(self):
        if CAMPAIGN_TIMELINE_PATH.exists():
            md_text = load_markdown(CAMPAIGN_TIMELINE_PATH)
            body = (
                "<h1>Campaign Timeline</h1>"
                "<p>First introductions for campaign entities, rendered from Mermaid markdown.</p>"
                f"<div class='meta'>Source: <code>{html.escape(str(CAMPAIGN_TIMELINE_PATH))}</code></div>"
                + markdown_to_html(md_text)
            )
        else:
            body = (
                "<h1>Campaign Timeline</h1>"
                "<div class='card'>"
                "<p>The campaign intro timeline has not been generated yet.</p>"
                "<p class='meta'>Run one of these commands, then refresh this page:</p>"
                "<pre><code>python3 03_organization/build_campaign_intro_timeline.py\n"
                "python3 scripts/build_campaign_intro_timeline.py</code></pre>"
                "</div>"
            )
        self.respond_html(render_page('Campaign Timeline', body))

    def serve_data_diagnostics(self, articles):
        manifest_count = 0
        campaign_manifest = 0
        general_manifest = 0
        if MANIFEST_PATH.exists():
            for line in MANIFEST_PATH.read_text(encoding='utf-8', errors='replace').splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                manifest_count += 1
                if str(row.get('scope', '')).lower() == 'campaign':
                    campaign_manifest += 1
                elif str(row.get('scope', '')).lower() == 'general':
                    general_manifest += 1

        queue_rows = read_queue()
        player_rows = read_player_input()

        by_cat = {}
        for a in articles.values():
            by_cat[a.category] = by_cat.get(a.category, 0) + 1

        cards = [
            '<h1>Data Diagnostics</h1>',
            '<p>Coverage snapshot of loaded wiki data, manifest state, and incoming suggestion queues.</p>',
            '<div class="card"><h3>Loaded Articles</h3><ul>'
        ]
        for k in sorted(by_cat):
            cards.append(f'<li><strong>{html.escape(k)}</strong>: {by_cat[k]}</li>')
        cards.append(f'<li><strong>Total</strong>: {len(articles)}</li>')
        cards.append('</ul></div>')

        cards.append('<div class="card"><h3>Manifest Coverage</h3><ul>')
        cards.append(f'<li>Manifest path: <code>{html.escape(str(MANIFEST_PATH))}</code></li>')
        cards.append(f'<li>Rows: {manifest_count}</li>')
        cards.append(f'<li>Campaign entities: {campaign_manifest}</li>')
        cards.append(f'<li>General entities: {general_manifest}</li>')
        cards.append('</ul></div>')

        cards.append('<div class="card"><h3>Incoming Suggestions</h3><ul>')
        cards.append(f'<li>Entity request queue items: {len(queue_rows)}</li>')
        cards.append(f'<li>Player submissions: {len(player_rows)}</li>')
        if queue_rows:
            latest_q = sorted(queue_rows, key=lambda x: x.get('ts', 0), reverse=True)[:5]
            cards.append('<li>Latest queue entries:<ul>')
            for r in latest_q:
                ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r.get('ts', 0)))
                cards.append(f"<li>{html.escape(r.get('entity',''))} — <span class='meta'>{ts}</span></li>")
            cards.append('</ul></li>')
        cards.append('</ul></div>')

        self.respond_html(render_page('Data Diagnostics', ''.join(cards)))

    def serve_source_debug(self, parsed):
        q = parse_qs(parsed.query)
        src = (q.get('path', [''])[0] or '')
        p = safe_source_path(src)
        if not p:
            body = (
                '<h1>Source Debug View</h1>'
                '<div class="card"><p>Provide a source path with <code>?path=...</code>.</p>'
                '<p class="meta">Allowed roots include cleaned memory, raw source root, and data root.</p></div>'
            )
            self.respond_html(render_page('Source Debug', body))
            return
        if not p.exists() or not p.is_file():
            self.respond_html(render_page('Source Debug', f"<h1>Source Debug View</h1><div class='card'><p>Not found: <code>{html.escape(str(p))}</code></p></div>"))
            return

        if p.suffix.lower() == '.jsonl':
            lines = p.read_text(encoding='utf-8', errors='replace').splitlines()[:500]
            content = '\n'.join(lines)
        else:
            content = p.read_text(encoding='utf-8', errors='replace')
            lines = content.splitlines()[:1200]
            content = '\n'.join(lines)

        body = (
            '<h1>Source Debug View</h1>'
            f"<div class='meta'>Source: <code>{html.escape(str(p))}</code></div>"
            f"<div class='card'><pre><code>{html.escape(content)}</code></pre></div>"
        )
        self.respond_html(render_page('Source Debug', body))

    def serve_article(self, articles, inbound_count, inbound_sources, pattern, name_to_slug, slug):
        a = articles.get(slug)
        if not a:
            self.send_error(404, 'Article not found')
            return
        raw_html = markdown_to_html(a.body)
        linked_html, refs = autolink_html(raw_html, slug, pattern, name_to_slug)
        entity_name = a.title.replace('Campaign NPC: ', '').replace('Campaign PC: ', '').replace('Campaign Entity: ', '').strip()
        input_form = (
            '<div class="card"><h3>Contribute / Request Update</h3>'
            '<form method="POST" action="/player-input-add">'
            f'<input type="hidden" name="target_slug" value="{html.escape(slug)}" />'
            f'<input type="hidden" name="entity" value="{html.escape(entity_name)}" />'
            '<label>Player name</label><input name="player" placeholder="Your name" />'
            f'<label>Entity</label><input value="{html.escape(entity_name)}" disabled />'
            '<label>Request type</label><select name="request_type"><option value="fact">Fact</option><option value="update">Update</option><option value="research">Research request</option><option value="question">Question</option></select>'
            '<label>Submission</label><textarea name="note" rows="3" placeholder="Add facts, corrections, or request research"></textarea>'
            '<button type="submit">Submit</button></form></div>'
        )

        meta = (
            f'<div class="meta">Category: <strong>{html.escape(a.category)}</strong> '
            f'| Referenced by <strong>{inbound_count.get(slug,0)}</strong> items '
            f'| Outbound links: <strong>{len(refs)}</strong>'
        )
        if a.path:
            src_q = quote(str(a.path))
            meta += f' | Source: <a href="/debug/source?path={src_q}"><code>{html.escape(str(a.path))}</code></a>'
        meta += '</div>'

        backlink_block = ['<div class="card"><h3>Referenced by</h3>']
        refs = inbound_sources.get(slug, [])
        if not refs:
            backlink_block.append('<p class="meta">No inbound references recorded.</p>')
        else:
            backlink_block.append('<ul>')
            for src in sorted(set(refs)):
                src_a = articles.get(src)
                title = src_a.title if src_a else src
                backlink_block.append(f'<li><a href="/article/{quote(src)}">{html.escape(title)}</a></li>')
            backlink_block.append('</ul>')
        backlink_block.append('</div>')

        self.respond_html(render_page(a.title, input_form + meta + linked_html + ''.join(backlink_block)))

    def respond_html(self, body: str):
        data = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8889)
    args = ap.parse_args()
    server = ThreadingHTTPServer(('0.0.0.0', args.port), WikiHandler)
    print(f'Knowledge wiki listening on http://127.0.0.1:{args.port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
