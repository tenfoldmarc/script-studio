#!/usr/bin/env python3
"""Script Studio dashboard: the buyer's research on one page, in their own branding.

  PY dashboard.py [--open]

Reads the buyer's Script Studio folder (env SCRIPT_STUDIO_STATE, else the per-OS data folder for 'script-studio',
the same folder ss.py uses) and writes <state>/dashboard/index.html, one self-contained page, plus the images it
shows in <state>/dashboard/img/. Prints one line: DASHBOARD <path>. --open opens it in the default browser.
Standard library only, Python 3.9+. Never writes outside <state>/dashboard/.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
APP = 'script-studio'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ScriptStudio/1.0'
FRESH_DAYS = 3


# ---------- folders (same resolution as ss.py) ----------

def data_dir(app):
    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        return os.path.join(home, 'Library', 'Application Support', app)
    if sys.platform.startswith('win'):
        return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.join(home, 'AppData', 'Local'), app)
    xdg = os.environ.get('XDG_DATA_HOME') or ''
    return os.path.join(xdg if xdg.startswith('/') else os.path.join(home, '.local', 'share'), app)


ST = os.environ.get('SCRIPT_STUDIO_STATE') or data_dir(APP)
OUT = os.path.join(ST, 'dashboard')
IMG = os.path.join(OUT, 'img')


def read_json(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return fallback


def read_text(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read()
    except Exception:
        return ''


# ---------- formatting ----------

def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def fmt_n(n):
    n = n or 0
    if n >= 1_000_000:
        return '%.1fM' % (n / 1e6)
    if n >= 1000:
        return '%.1fK' % (n / 1e3)
    return str(int(n))


def fmt_x(x):
    x = x or 0
    if x < 0.1:
        return 'under 0.1x'
    return '%.1fx' % x


def fmt_len(sec):
    sec = int(round(sec or 0))
    if not sec:
        return ''
    return '%ds' % sec if sec < 60 else '%d:%02d' % (sec // 60, sec % 60)


def fmt_ts(sec):
    sec = int(sec or 0)
    return '%d:%02d' % (sec // 60, sec % 60)


def parse_ts(s):
    s = (s or '').strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        pass
    for f in ('%a %b %d %H:%M:%S %z %Y', '%Y-%m-%d'):
        try:
            d = dt.datetime.strptime(s, f)
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pass
    return None


def fmt_date(s, with_year=False):
    d = parse_ts(s) if isinstance(s, str) else s
    if not d:
        return ''
    out = d.strftime('%b ') + str(d.day)
    if with_year or d.year != dt.date.today().year:
        out += ', %d' % d.year
    return out


def ago(day):
    if not day:
        return ''
    n = (dt.date.today() - day).days
    return 'today' if n <= 0 else 'yesterday' if n == 1 else '%d days ago' % n


def first_line(s, n=140):
    s = (s or '').strip().split('\n')[0].strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def md_inline(s):
    """Escaped text with **bold** kept."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', esc(s))


# ---------- color ----------

HEX = re.compile(r'^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def norm_hex(v, fallback):
    m = HEX.match((v or '').strip()) if isinstance(v, str) else None
    if not m:
        return fallback
    h = m.group(1)
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return '#' + h.lower()


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def to_hex(c):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v)))) for v in c)


def mix(a, b, t):
    ra, rb = rgb(a), rgb(b)
    return to_hex(tuple(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))


def rgba(h, a):
    r, g, b = rgb(h)
    return 'rgba(%d,%d,%d,%.3f)' % (r, g, b, a)


def lum(h):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def lift(fg, bg, toward, need=4.5):
    """Move fg toward `toward` until it reads on bg."""
    for _ in range(20):
        if contrast(fg, bg) >= need:
            break
        fg = mix(fg, toward, 0.12)
    return fg


DEFAULT_BRAND = {
    'name': '',
    'colors': {'bg': '#101113', 'surface': '#18191c', 'text': '#eceae5', 'muted': '#a3a29d',
               'accent': '#c9a46a', 'accent2': '#e3c48c'},
    'fonts': {'heading': 'Instrument Serif', 'body': 'Inter'},
    'google_fonts_url': 'https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Inter:wght@400;500;600;700&display=swap',
    'logo': '',
    'mode': 'dark',
    'source': 'default',
}


def font_stack(name, serif_hint=False):
    name = re.sub(r'[^A-Za-z0-9 \-]', '', name or '').strip()
    low = name.lower()
    tail = 'Georgia, "Times New Roman", serif' if (serif_hint or ('serif' in low and 'sans' not in low)) else \
        'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
    return ('"%s", %s' % (name, tail)) if name else tail


def font_weights(url, family):
    """Weights the Google Fonts link loads for this family (empty: only the regular one)."""
    q = urllib.parse.urlparse(url or '').query
    for fam in urllib.parse.parse_qs(q).get('family', []):
        nm, _, spec = fam.partition(':')
        if nm.replace('+', ' ').strip().lower() == (family or '').lower():
            return [int(w) for w in re.findall(r'\d{3}', spec.split('@')[-1])] if '@' in spec else []
    return []


def load_brand():
    raw = read_json(os.path.join(ST, 'brand.json'), None)
    is_default = not isinstance(raw, dict)
    b = json.loads(json.dumps(DEFAULT_BRAND))
    if not is_default:
        for k in ('name', 'logo', 'mode', 'source', 'google_fonts_url'):
            if isinstance(raw.get(k), str):
                b[k] = raw[k].strip()
        for grp in ('colors', 'fonts'):
            if isinstance(raw.get(grp), dict):
                for k, v in raw[grp].items():
                    if isinstance(v, str) and v.strip():
                        b[grp][k] = v.strip()
        if not raw.get('google_fonts_url') and isinstance(raw.get('fonts'), dict):
            b['google_fonts_url'] = ''
    d = DEFAULT_BRAND['colors']
    c = {k: norm_hex(b['colors'].get(k), d[k]) for k in d}
    light = (b.get('mode') or '').lower() == 'light' or (b.get('mode') not in ('dark', 'light') and lum(c['bg']) > 0.4)
    ink, paper = ('#111111', '#ffffff')
    if contrast(c['text'], c['bg']) < 4.5:
        c['text'] = ink if contrast(ink, c['bg']) > contrast(paper, c['bg']) else paper
    if contrast(c['text'], c['surface']) < 4.5:
        c['surface'] = mix(c['bg'], c['text'], 0.05)
    c['muted'] = lift(c['muted'], c['surface'], c['text'])
    c['accent2'] = lift(c['accent2'], c['surface'], c['text'])
    # a solid accent fill (badges, the active button) with a readable label on it
    fill = c['accent']
    best = max((c['text'], c['bg'], paper, ink), key=lambda f: contrast(f, fill))
    toward = '#000000' if lum(best) > 0.5 else '#ffffff'
    for _ in range(14):
        if contrast(best, fill) >= 4.5:
            break
        fill = mix(fill, toward, 0.07)
    c['fill'], c['on_fill'] = fill, best
    fonts = b['fonts']
    url = b.get('google_fonts_url') or ''
    if not url.startswith('https://fonts.googleapis.com/'):
        url = ''
    links = [url] if url else []
    if not url and (fonts.get('heading') or fonts.get('body')):
        for i, fam in enumerate([fonts.get('heading'), fonts.get('body')]):
            if fam and fam.lower() not in ('system-ui', 'georgia', 'arial', 'helvetica'):
                spec = urllib.parse.quote_plus(fam) + ('' if i == 0 else ':wght@400;500;600;700')
                links.append('https://fonts.googleapis.com/css2?family=%s&display=swap' % spec)
    hw = [w for w in font_weights(url, fonts.get('heading')) if w <= 800]
    heading_w = 700 if 700 in hw else (max(hw) if hw else 400)
    return {
        'c': c, 'light': light, 'links': links, 'default': is_default, 'name': b.get('name') or '',
        'logo': b.get('logo') or '', 'source': b.get('source') or '',
        'hfont': font_stack(fonts.get('heading'), serif_hint='serif' in (fonts.get('heading') or '').lower()),
        'bfont': font_stack(fonts.get('body')), 'hw': heading_w,
    }


def css_vars(br):
    c = br['c']
    light = br['light']
    return ':root{color-scheme:%s;--bg:%s;--surface:%s;--surface2:%s;--text:%s;--muted:%s;--accent:%s;--accent2:%s;' \
           '--fill:%s;--on-fill:%s;--line:%s;--line2:%s;--soft:%s;--glow:%s;--shade:%s;--hfont:%s;--bfont:%s;--hw:%d}' % (
               'light' if light else 'dark', c['bg'], c['surface'], mix(c['surface'], c['text'], 0.045), c['text'],
               c['muted'], c['accent'], c['accent2'], c['fill'], c['on_fill'], rgba(c['text'], 0.09),
               rgba(c['text'], 0.17), rgba(c['accent2'], 0.13), rgba(c['accent'], 0.22 if not light else 0.14),
               'rgba(10,12,14,.10)' if light else 'rgba(0,0,0,.38)', br['hfont'], br['bfont'], br['hw'])


# ---------- the research ----------

def counts(r):
    return not r.get('fresh') and not r.get('pinned') and not r.get('repeat') and (r.get('views') or 0) > 0


def reel_dir(h, code):
    return os.path.join(ST, 'library', h, code)


def segments(h, code):
    d = read_json(os.path.join(reel_dir(h, code), 'transcript.json'), None) or {}
    return [s for s in d.get('segments', []) if isinstance(s, dict) and s.get('text')]


def transcript_text(h, code):
    return read_text(os.path.join(reel_dir(h, code), 'transcript.txt')).strip()


def hook_line(h, code, secs=4.0):
    segs = segments(h, code)
    if segs:
        out = ' '.join(s['text'].strip() for s in segs if (s.get('start') or 0) < secs).strip()
        if out:
            return out
    t = transcript_text(h, code)
    return ' '.join(t.split()[:14]) + ('…' if len(t.split()) > 14 else '') if t else ''


def load_libraries():
    libs = {}
    root = os.path.join(ST, 'library')
    for h in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = read_json(os.path.join(root, h, 'reels.json'), None)
        if isinstance(d, dict) and isinstance(d.get('reels'), list):
            for r in d['reels']:
                r.setdefault('x', 0)
                r.setdefault('views', 0)
            libs[h] = d
    return libs


def parse_hook_bank():
    out = []
    for line in read_text(os.path.join(ST, 'hook-bank.md')).splitlines():
        if line.strip().lower().startswith('why:') and out:
            out[-1]['why'] = line.strip()[4:].strip()
            continue
        if ' | ' not in line or line.startswith(('#', 'Format', 'Append')):
            continue
        f = [x.strip() for x in line.split(' | ')]
        i = next((k for k, v in enumerate(f) if re.match(r'https?://', v)), None)
        if i is None or i < 3:
            continue
        mech, _, surface = f[i - 2].partition('@')
        stat = f[i + 1] if len(f) > i + 1 else ''
        m = re.search(r'([\d.]+)\s*x', stat)
        creator = f[i + 2] if len(f) > i + 2 else ''
        out.append({
            'template': ' | '.join(f[:i - 2]), 'mechs': [x.strip() for x in mech.split('+') if x.strip()],
            'surface': surface.strip(), 'original': f[i - 1], 'url': f[i], 'stat': stat,
            'x': float(m.group(1)) if m else 0, 'views': stat.split(',')[0].strip() if ',' in stat else '',
            'creator': creator, 'self': creator.strip().lower() in ('self', 'you', 'me'), 'why': '',
        })
    out.sort(key=lambda e: e['x'], reverse=True)
    return out


def md_sections(text):
    secs, cur = {}, None
    for line in text.splitlines():
        m = re.match(r'^##\s+(.+?)\s*$', line)
        if m:
            cur = m.group(1).strip().lower()
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return secs


def bullets(lines):
    out = []
    for ln in lines:
        m = re.match(r'^\s*[-*]\s+(.+)$', ln)
        if m:
            out.append(m.group(1).strip())
        elif re.match(r'^\s*\d+[.)]\s+(.+)$', ln):
            out.append(re.sub(r'^\s*\d+[.)]\s+', '', ln).strip())
    return out


def split_title(s):
    s = re.sub(r'\s*\[(inferred|confirmed|likely)[^\]]*\]\s*$', '', s)
    for sep in (' | ', ': '):
        if sep in s:
            a, b = s.split(sep, 1)
            if len(a) <= 90:
                return a.strip().strip('*'), b.strip()
    return s.strip('*'), ''


def latest_radar(kind):
    d = os.path.join(ST, 'research', 'radar')
    fs = [f for f in (os.listdir(d) if os.path.isdir(d) else []) if f.startswith(kind + '-') and f.endswith('.json')]
    if not fs:
        return [], None
    f = max(fs, key=lambda f: os.path.getmtime(os.path.join(d, f)))
    m = re.search(r'(\d{4}-\d{2}-\d{2})', f)
    data = read_json(os.path.join(d, f), []) or []
    return (data if isinstance(data, list) else []), (m.group(1) if m else None)


BOT = ('i am a bot', 'automoderator', 'featured it on our discord', 'welcome to r/', 'welcome to /r/',
       'your post has been removed', 'contact the moderators', 'this is an automated')


def good_comment(c):
    t = (c or '').strip()
    return bool(t) and t.lower() not in ('[deleted]', '[removed]') and not any(b in t.lower() for b in BOT)


# ---------- images ----------

def safe_name(h, code):
    return re.sub(r'[^A-Za-z0-9._-]', '_', '%s--%s' % (h, code))


def image_job(h, r):
    """(key, kind, source) for the picture of a reel: its first frame if transcribed, else its cover."""
    d = reel_dir(h, r.get('code') or '')
    for f in (r.get('frames') or []) + ['frame-0.jpg', 'frame-2.jpg']:
        p = os.path.join(d, f)
        if os.path.isfile(p):
            return (safe_name(h, r['code']), 'copy', p)
    if r.get('cover_url'):
        return (safe_name(h, r['code']), 'get', r['cover_url'])
    return None


MAGIC = ((b'\xff\xd8\xff', '.jpg'), (b'\x89PNG', '.png'), (b'RIFF', '.webp'))


def run_image_job(job):
    key, kind, src = job
    for ext in ('.jpg', '.png', '.webp'):
        dest = os.path.join(IMG, key + ext)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            if kind == 'get' or os.path.getmtime(dest) >= os.path.getmtime(src):
                return key, 'img/' + key + ext
    try:
        if kind == 'copy':
            dest = os.path.join(IMG, key + '.jpg')
            shutil.copyfile(src, dest)
            return key, 'img/' + key + '.jpg'
        req = urllib.request.Request(src, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read(6 * 1024 * 1024 + 1)
        if len(data) > 6 * 1024 * 1024:
            return key, None
        ext = next((e for m, e in MAGIC if data.startswith(m)), None)
        if not ext:
            return key, None
        dest = os.path.join(IMG, key + ext)
        with open(dest + '.part', 'wb') as fh:
            fh.write(data)
        os.replace(dest + '.part', dest)
        return key, 'img/' + key + ext
    except Exception:
        return key, None


def prepare_images(jobs):
    os.makedirs(IMG, exist_ok=True)
    uniq = {}
    for j in jobs:
        if j and j[0] not in uniq:
            uniq[j[0]] = j
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(run_image_job, uniq.values()))


def copy_logo(path):
    if not path:
        return None
    p = path if os.path.isabs(path) else os.path.join(ST, path)
    p = os.path.expanduser(p)
    ext = os.path.splitext(p)[1].lower()
    if not os.path.isfile(p) or ext not in ('.png', '.jpg', '.jpeg', '.svg', '.webp'):
        return None
    os.makedirs(IMG, exist_ok=True)
    try:
        shutil.copyfile(p, os.path.join(IMG, 'logo' + ext))
        return 'img/logo' + ext
    except Exception:
        return None


# ---------- page pieces ----------

def say(cmd):
    return '<p class="say"><span>Say</span><b>%s</b></p>' % esc(cmd)


def empty(title, body, cmd=None):
    return '<div class="empty"><p class="e-title">%s</p><p>%s</p>%s</div>' % (esc(title), esc(body), say(cmd) if cmd else '')


def thumb_html(src, h, alt):
    if src:
        return '<img src="%s" alt="%s" loading="lazy" decoding="async">' % (esc(src), esc(alt))
    return '<div class="noimg"><span>%s</span><small>No preview</small></div>' % esc((h or '?')[:1].upper())


def reel_detail(h, r, img, whose, note=''):
    """The full view of a reel, shown in the dialog."""
    segs = segments(h, r['code'])
    text = transcript_text(h, r['code'])
    if segs:
        body = ''.join('<p class="tline%s"><span class="ts">%s</span><span>%s</span></p>' % (
            ' is-hook' if (s.get('start') or 0) < 4 else '', fmt_ts(s.get('start')), esc(s['text'].strip())) for s in segs)
        tr = '<h4>What was said</h4><p class="hint">The highlighted lines are the first 4 seconds: the spoken hook.</p><div class="transcript">%s</div>' % body
    elif text:
        tr = '<h4>What was said</h4><div class="transcript"><p>%s</p></div>' % esc(text)
    else:
        tr = '<h4>What was said</h4>' + (empty('Not transcribed yet', 'This one gets transcribed in a later refresh once it has settled.', 'refresh my research')
                                         if whose == 'your' else empty('Not transcribed yet', 'Want the exact words? Ask for this reel by its link.', 'transcribe this reel ' + r.get('url', '')))
    cap = (r.get('caption') or '').strip()
    coms = [c for c in (r.get('top_comments') or []) if good_comment(c)][:6]
    stats = [('%s' % fmt_n(r.get('views')), 'views'), (fmt_n(r.get('likes')), 'likes'), (fmt_n(r.get('comments')), 'comments')]
    if r.get('duration'):
        stats.append((fmt_len(r['duration']), 'long'))
    return (
        '<div class="d-grid"><div class="d-media">%s</div><div class="d-info">'
        '<p class="d-eyebrow">@%s · posted %s</p>'
        '<p class="d-x"><b>%s</b> %s usual</p>%s'
        '<div class="d-stats">%s</div>'
        '<a class="btn" href="%s" target="_blank" rel="noopener">Open the post <span aria-hidden="true">↗</span></a>'
        '%s%s%s</div></div>') % (
        thumb_html(img, h, 'First frame of the reel'), esc(h), esc(fmt_date(r.get('posted'), True)),
        esc(fmt_x(r.get('x'))), whose, ('<p class="d-note">%s</p>' % esc(note)) if note else '',
        ''.join('<span><b>%s</b>%s</span>' % (esc(a), esc(b)) for a, b in stats), esc(r.get('url', '#')), tr,
        ('<h4>Caption</h4><p class="d-cap">%s</p>' % esc(cap).replace('\n', '<br>')) if cap else '',
        ('<h4>What people commented</h4><ul class="d-coms">%s</ul>' % ''.join('<li>%s</li>' % esc(first_line(c, 300)) for c in coms)) if coms else '')


class Page:
    def __init__(self):
        self.templates = []
        self.n = 0

    def detail(self, html_body):
        self.n += 1
        tid = 'd%d' % self.n
        self.templates.append('<template id="%s">%s</template>' % (tid, html_body))
        return tid


def reel_card(pg, h, r, img, whose, rank=None, label=None, group='', hide=False):
    hook = hook_line(h, r['code']) if r.get('transcribed') or os.path.isfile(os.path.join(reel_dir(h, r['code']), 'transcript.json')) else ''
    cap = first_line(r.get('caption'), 160)
    x = r.get('x') or 0
    tone = 'win' if x >= 1.2 else ('weak' if x < 0.7 else 'mid')
    note = ''
    if label:
        note = label[1]
    tid = pg.detail(reel_detail(h, r, img, whose, note))
    flags = ''
    if r.get('collab'):
        flags += '<span class="flag">Collab or paid: weigh lightly</span>'
    if label:
        flags += '<span class="flag grey">%s</span>' % esc(label[0])
    main = ('<p class="k">Spoken hook</p><p class="hook">“%s”</p>' % esc(first_line(hook, 220))) if hook else \
        ('<p class="k">Caption</p><p class="hook">%s</p>' % esc(cap or 'No caption'))
    capline = ('<p class="cap">%s</p>' % esc(cap)) if (hook and cap) else ''
    meta = [fmt_n(r.get('views')) + ' views', fmt_date(r.get('posted')), fmt_len(r.get('duration'))]
    return (
        '<article class="card reel%s%s" data-group="%s" data-open="%s" tabindex="0" role="button" aria-label="Open details for this reel">'
        '<div class="thumb">%s<span class="badge %s">%s <em>%s usual</em></span>%s</div>'
        '<div class="c-body">%s%s%s<div class="meta">%s</div>'
        '<div class="c-foot"><span class="more-link">%s</span><a href="%s" target="_blank" rel="noopener" class="ext">Open post <span aria-hidden="true">↗</span></a></div>'
        '</div></article>') % (
        ' is-off' if label else '', ' is-more' if hide else '', group, tid, thumb_html(img, h, 'Reel by @' + h),
        'off' if label else tone, esc(fmt_x(x)), whose, ('<span class="rank">%d</span>' % rank) if rank else '',
        flags and '<div class="flags">%s</div>' % flags, main, capline,
        ''.join('<span>%s</span>' % esc(m) for m in meta if m),
        'Read transcript' if hook else 'Details', esc(r.get('url', '#')))


def off_label(r):
    if r.get('fresh'):
        n = r.get('age_days')
        when = 'today' if n == 0 else ('yesterday' if n == 1 else '%s days ago' % n) if n is not None else 'recently'
        return ('Too new to judge', 'Posted %s. Views are still climbing, so it does not count yet.' % when)
    if r.get('repeat'):
        return ('Repeat of another reel', 'The same video was posted twice. Only the stronger copy counts.')
    if r.get('pinned'):
        return ('Pinned', 'Pinned reels keep collecting views, so they are left out of the ranking.')
    if r.get('suspect'):
        return ('Check this one', 'Under a tenth of the usual views. Usually a re-upload or a post Instagram held back, not a real flop.')
    return None


def pulse_chart(reels, med):
    """Every settled reel, oldest to newest, above or below the usual (log scale)."""
    import math
    rs = sorted(reels, key=lambda r: r.get('posted') or '')
    if len(rs) < 3:
        return ''
    xs = [max(0.1, r['x'] or 0.1) for r in rs]
    up = max(math.log10(max(xs)), 0.3)
    dn = max(math.log10(1 / min(xs)), 0.3)
    bars = []
    for r, x in zip(rs, xs):
        v = math.log10(x)
        cls = 'win' if x >= 1.2 else ('weak' if x < 0.7 else 'mid')
        pct = abs(v) / (up if v >= 0 else dn) * 100
        bars.append('<a class="pb %s" href="%s" target="_blank" rel="noopener" title="%s · %s views · %s your usual">'
                    '<i style="--h:%.1f%%" class="%s"></i></a>' % (
                        cls, esc(r.get('url', '#')), esc(fmt_date(r.get('posted'))), esc(fmt_n(r.get('views'))),
                        esc(fmt_x(x)), max(pct, 2.5), 'u' if v >= 0 else 'd'))
    best = max(rs, key=lambda r: r['x'])
    return ('<figure class="pulse"><figcaption><span>Every settled reel, oldest to newest</span>'
            '<span class="pl"><span><i class="sw win"></i>above your usual</span><span><i class="sw weak"></i>below</span><span><i class="sw line"></i>your usual, %s views</span></span></figcaption>'
            '<div class="pchart" style="--up:%.3f;--dn:%.3f"><div class="mid-line"></div>%s</div>'
            '<p class="pcap">Tallest bar: %s your usual, %s.</p></figure>') % (
        esc(fmt_n(med)), up / (up + dn), dn / (up + dn), ''.join(bars), esc(fmt_x(best['x'])), esc(fmt_date(best.get('posted'))))


# ---------- sections ----------

def section_my_reels(pg, own, od, imgs):
    if not own:
        return empty('No account set up yet', 'Tell Claude your Instagram handle and it studies your reels for you.', 'set up Script Studio')
    if not od:
        return empty('Your reels are not studied yet', 'Claude collects your public reels, ranks them against your own usual and transcribes the best and the weakest.', 'refresh my research')
    reels = od['reels']
    ranked = sorted([r for r in reels if counts(r) and not r.get('suspect')], key=lambda r: r['x'], reverse=True)
    off = [r for r in reels if not (counts(r) and not r.get('suspect'))]
    n_win = sum(1 for r in ranked if r['x'] >= 1.2)
    n_weak = sum(1 for r in ranked if r['x'] < 0.7)
    cards = []
    for i, r in enumerate(ranked, 1):
        g = 'win' if r['x'] >= 1.2 else ('weak' if r['x'] < 0.7 else 'mid')
        cards.append(reel_card(pg, own, r, imgs.get(safe_name(own, r['code'])), 'your', rank=i, group=g))
    seg = ('<div class="seg" role="group" aria-label="Filter your reels">'
           '<button class="on" data-filter="all">All <span>%d</span></button>'
           '<button data-filter="win">Winners, 1.2x+ <span>%d</span></button>'
           '<button data-filter="weak">Weakest, under 0.7x <span>%d</span></button></div>') % (len(ranked), n_win, n_weak)
    out = ['<div class="sec-head"><div><h2>My reels</h2><p>Ranked by how far each one beat your usual. Tap a reel to read exactly what you said.</p></div>%s</div>' % seg]
    out.append(pulse_chart(ranked, od.get('median_views')))
    if cards:
        out.append('<div class="grid reels" id="my-grid">%s</div>' % ''.join(cards))
        out.append('<div class="empty filter-empty" hidden><p class="e-title">Nothing in this group yet</p><p>Try another filter.</p></div>')
    else:
        out.append(empty('No settled reels yet', 'Reels need about 3 days before their views settle. Check back after your next refresh.', 'refresh my research'))
    if off:
        off.sort(key=lambda r: r.get('posted') or '', reverse=True)
        oc = [reel_card(pg, own, r, imgs.get(safe_name(own, r['code'])), 'your', label=off_label(r), hide=i >= 8) for i, r in enumerate(off)]
        more = ('<button class="more" data-more>Show all %d</button>' % len(off)) if len(off) > 8 else ''
        out.append('<div class="sub-head"><h3>Not counted yet</h3><p>Too new, a repeat, or suspiciously low. They never count toward your usual or the ranking.</p></div>'
                   '<div class="grid reels off-grid">%s</div>%s' % (''.join(oc), more))
    return ''.join(out)


def section_hooks(pg, own, od, imgs, bank, voice):
    out = ['<div class="sec-head"><div><h2>My hook library</h2><p>Opening lines that already won, as templates you can reuse. Your own first, then the best from around you.</p></div></div>']
    wins = []
    if od:
        for r in sorted([r for r in od['reels'] if counts(r) and not r.get('suspect') and r['x'] >= 1.2], key=lambda r: r['x'], reverse=True):
            hk = hook_line(own, r['code'])
            if hk:
                wins.append((r, hk))
    out.append('<div class="sub-head"><h3>Your winning openers</h3><p>The first 4 seconds of your reels that beat your usual.</p></div>')
    if wins:
        rows = []
        for r, hk in wins[:10]:
            img = imgs.get(safe_name(own, r['code']))
            tid = pg.detail(reel_detail(own, r, img, 'your'))
            rows.append('<article class="opener" data-open="%s" tabindex="0" role="button"><div class="o-thumb">%s</div><div class="o-body">'
                        '<p class="hook">“%s”</p><p class="meta"><b class="xnum">%s your usual</b><span>%s views</span><span>%s</span></p></div>'
                        '<a class="ext" href="%s" target="_blank" rel="noopener" aria-label="Open the post">↗</a></article>' % (
                            tid, thumb_html(img, own, 'Your reel'), esc(first_line(hk, 200)), esc(fmt_x(r['x'])),
                            esc(fmt_n(r['views'])), esc(fmt_date(r.get('posted'))), esc(r.get('url', '#'))))
        out.append('<div class="openers">%s</div>' % ''.join(rows))
    else:
        out.append(empty('No winning openers yet', 'Once a few of your reels beat your usual and get transcribed, their first lines land here.', 'refresh my research'))
    secs = md_sections(voice)
    lean = bullets(secs.get('hook types they lean on', []))
    if lean:
        items = []
        for b in lean:
            b = re.sub(r'\bfor (him|her|them)\b', 'for you', re.sub(r'\s*\[(inferred|confirmed|likely)[^\]]*\]\s*$', '', b))
            left, _, quote = b.partition(' | ')
            name, stat = left, ''
            m = re.match(r'^(.*?\S)(?::\s+)([^:]*)$', left)
            if m and len(m.group(1)) < 140:
                name, stat = m.group(1), m.group(2)
            weak = name.lower().startswith(('weak', 'avoid', 'flop'))
            items.append('<li class="%s"><p class="ln">%s</p>%s%s</li>' % (
                'weak' if weak else '', md_inline(name), ('<p class="ls">%s</p>' % md_inline(stat)) if stat else '',
                ('<p class="lq">%s</p>' % md_inline(quote)) if quote else ''))
        out.append('<div class="sub-head"><h3>The hook types that work for you</h3><p>From your voice profile.</p></div><ul class="lean">%s</ul>' % ''.join(items))
    out.append('<div class="sub-head"><h3>Hook bank</h3><p>Every saved hook, best first. The words in color are the parts you swap for your own.</p></div>')
    if not bank:
        out.append(empty('Your hook bank is empty', 'Claude fills it from the reels that beat their creator\'s usual, yours and your competitors\'.', 'refresh my research'))
        return ''.join(out)
    mechs = {}
    for e in bank:
        for m in e['mechs']:
            mechs[m] = mechs.get(m, 0) + 1
    chips = '<button class="chip on" data-mech="">All <span>%d</span></button>' % len(bank) + ''.join(
        '<button class="chip" data-mech="%s">%s <span>%d</span></button>' % (esc(m.lower()), esc(m), n)
        for m, n in sorted(mechs.items(), key=lambda kv: (-kv[1], kv[0])))
    out.append('<div class="bank-tools"><label class="search"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/></svg>'
               '<input type="search" id="hook-q" placeholder="Search hooks, words, creators" aria-label="Search the hook bank"></label>'
               '<div class="chips" role="group" aria-label="Filter by hook type">%s</div></div>' % chips)
    cards = []
    for e in bank:
        tpl = re.sub(r'\[([^\]]+)\]', r'<span class="slot">\1</span>', esc(e['template']))
        who = 'You' if e['self'] else e['creator']
        whose = 'your' if e['self'] else 'their'
        surface = {'spoken': 'the spoken line', 'on-screen': 'the on-screen text', 'frame one': 'the first frame',
                   'caption': 'the caption'}.get(e['surface'].lower(), e['surface'])
        text = ' '.join([e['template'], e['original'], e['why'], who, ' '.join(e['mechs'])]).lower()
        cards.append(
            '<article class="hookcard" data-mechs="%s" data-text="%s">'
            '<div class="h-top">%s%s</div>'
            '<p class="tpl">%s</p>'
            '<p class="orig"><span>Original</span>%s</p>%s'
            '<div class="h-foot"><span class="who%s">%s</span>%s<a class="ext" href="%s" target="_blank" rel="noopener">See it <span aria-hidden="true">↗</span></a></div>'
            '</article>' % (
                esc('|'.join(m.lower() for m in e['mechs'])), esc(text),
                ''.join('<span class="tag">%s</span>' % esc(m) for m in e['mechs']),
                ('<span class="tag ghost">Carried by %s</span>' % esc(surface)) if surface else '',
                tpl, esc(e['original']), ('<p class="why"><span>Why it works</span>%s</p>' % esc(e['why'])) if e['why'] else '',
                ' self' if e['self'] else '', esc(who),
                ('<span class="hx"><b>%s</b> %s usual%s</span>' % (esc(fmt_x(e['x'])), whose, (', %s views' % esc(e['views'])) if e['views'] else '')) if e['x'] else '',
                esc(e['url'])))
    out.append('<div class="bank" id="bank">%s</div><div class="empty bank-empty" hidden><p class="e-title">No hook matches that</p><p>Try a shorter word or another hook type.</p></div>' % ''.join(cards))
    return ''.join(out)


def section_competitors(pg, comps, libs, imgs):
    out = ['<div class="sec-head"><div><h2>Competitors</h2><p>The reels that beat their own usual by 2x or more. Their usual, not their follower count, is the bar.</p></div></div>']
    if not comps:
        out.append(empty('No competitors yet', 'Name 3 to 10 accounts whose reels pop in your space and Claude studies them.', 'add a competitor'))
        return ''.join(out)
    for h in comps:
        d = libs.get(h)
        head = '<div class="avatar">%s</div><div class="ch-txt"><h3>@%s</h3>%s</div><a class="ghost-btn" href="https://www.instagram.com/%s/" target="_blank" rel="noopener">Profile <span aria-hidden="true">↗</span></a>'
        if not d:
            out.append('<section class="comp"><header class="comp-head">%s</header>%s</section>' % (
                head % (esc(h[:1].upper()), esc(h), '<p>Not studied yet</p>', esc(h)),
                empty('Not studied yet', 'This account has not been collected. If it stays empty after a refresh, it is private or the handle is off.', 'refresh my research')))
            continue
        rs = d['reels']
        settled = [r for r in rs if counts(r)]
        outl = sorted([r for r in settled if r['x'] >= 2], key=lambda r: r['x'], reverse=True)
        climbing = sorted([r for r in rs if r.get('fresh') and r['x'] >= 2], key=lambda r: r['x'], reverse=True)[:3]
        best = max(settled, key=lambda r: r['x']) if settled else None
        sub = '<p>Usual reel: <b>%s views</b><span>%d reels studied</span>%s</p>' % (
            esc(fmt_n(d.get('median_views'))), len(rs), ('<span>Best: %s</span>' % esc(fmt_x(best['x']))) if best else '')
        cards = [reel_card(pg, h, r, imgs.get(safe_name(h, r['code'])), 'their', rank=i, hide=i > 6) for i, r in enumerate(outl, 1)]
        cards += [reel_card(pg, h, r, imgs.get(safe_name(h, r['code'])), 'their', label=off_label(r)) for r in climbing]
        body = ('<div class="grid reels">%s</div>' % ''.join(cards)) if cards else empty(
            'No breakout reels right now', 'None of their settled reels beat their usual by 2x. Their best so far: %s.' % (fmt_x(best['x']) if best else 'none'))
        more = ('<button class="more" data-more>Show all %d</button>' % len(outl)) if len(outl) > 6 else ''
        out.append('<section class="comp"><header class="comp-head">%s</header>%s%s</section>' % (
            head % (esc(h[:1].upper()), esc(h), sub, esc(h)), body, more))
    return ''.join(out)


def section_topics(voice, reddit, rdate, xs, xdate):
    out = ['<div class="sec-head"><div><h2>Topics</h2><p>What your audience is talking about right now, and the pillars your content stands on.</p></div></div>']
    pil = bullets(md_sections(voice).get('pillars', []))
    out.append('<div class="sub-head"><h3>Your pillars</h3><p>The few big themes every reel should fit under.</p></div>')
    if pil:
        out.append('<div class="pillars">%s</div>' % ''.join(
            '<div class="pillar"><span class="pn">%02d</span><p class="pt">%s</p>%s</div>' % (
                i, md_inline(t), ('<p class="pd">%s</p>' % md_inline(rest)) if rest else '')
            for i, (t, rest) in enumerate((split_title(b) for b in pil), 1)))
    else:
        out.append(empty('No pillars saved yet', 'Claude names your pillars from your best reels during a refresh.', 'refresh my research'))
    cols = []
    # Reddit
    if reddit:
        by = {}
        for it in sorted(reddit, key=lambda x: x.get('rank') or 99):
            by.setdefault(it.get('where') or 'Reddit', []).append(it)
        blocks = []
        for where, items in by.items():
            rows = []
            for i, it in enumerate(items):
                coms = [c for c in (it.get('top_comments') or []) if good_comment(c)][:3]
                text = first_line(it.get('text'), 260)
                rows.append(
                    '<article class="thread%s"><span class="t-rank">#%s</span><div class="t-body">'
                    '<a class="t-title" href="%s" target="_blank" rel="noopener">%s</a>%s%s'
                    '<p class="t-meta">Top of the %s%s</p></div></article>' % (
                        ' is-more' if i >= 6 else '', esc(it.get('rank') or i + 1), esc(it.get('url', '#')), esc(it.get('title') or 'Untitled'),
                        ('<p class="t-text">%s</p>' % esc(text)) if text else '',
                        ('<div class="t-coms"><p class="k">What people said</p>%s</div>' % ''.join('<blockquote>%s</blockquote>' % esc(first_line(c, 220)) for c in coms)) if coms else '',
                        esc(it.get('period') or 'week'), (' · %s' % esc(fmt_date(it.get('posted')))) if it.get('posted') else ''))
            more = ('<button class="more" data-more>Show all %d</button>' % len(items)) if len(items) > 6 else ''
            blocks.append('<div class="rgroup"><h4>%s <span>%d threads</span></h4>%s%s</div>' % (esc(where), len(items), ''.join(rows), more))
        cols.append('<div class="tcol"><div class="sub-head"><h3>Reddit</h3><p>The top threads in your subreddits%s.</p></div>%s</div>' % (
            (', collected %s' % esc(fmt_date(rdate))) if rdate else '', ''.join(blocks)))
    else:
        cols.append('<div class="tcol"><div class="sub-head"><h3>Reddit</h3></div>%s</div>' % empty(
            'No Reddit threads yet', 'Tell Claude the subreddits your audience reads and it pulls the top threads and comments.', 'add subreddits to my research'))
    if xs:
        posts = sorted(xs, key=lambda x: x.get('likes') or 0, reverse=True)
        rows = ''.join(
            '<article class="xpost%s"><p class="x-top"><b>%s</b><span>%s likes</span>%s</p><p class="x-text">%s</p>'
            '<a class="ext" href="%s" target="_blank" rel="noopener">Open on X <span aria-hidden="true">↗</span></a></article>' % (
                ' is-more' if i >= 8 else '', esc(p.get('where') or ''), esc(fmt_n(p.get('likes'))),
                ('<span>%s</span>' % esc(fmt_date(p.get('posted')))) if p.get('posted') else '',
                esc((p.get('text') or '').strip()).replace('\n', '<br>'), esc(p.get('url') or '#'))
            for i, p in enumerate(posts))
        more = ('<button class="more" data-more>Show all %d</button>' % len(posts)) if len(posts) > 8 else ''
        cols.append('<div class="tcol"><div class="sub-head"><h3>X</h3><p>Popular posts from the accounts and searches you follow%s.</p></div><div class="xlist">%s</div>%s</div>' % (
            (', collected %s' % esc(fmt_date(xdate))) if xdate else '', rows, more))
    else:
        cols.append('<div class="tcol"><div class="sub-head"><h3>X</h3></div>%s</div>' % empty(
            'No X posts yet', 'Give Claude a few X accounts or search terms and it pulls what is popular there.', 'add X searches to my research'))
    out.append('<div class="tcols">%s</div>' % ''.join(cols))
    return ''.join(out)


# ---------- page ----------

CSS = r"""
*,*::before,*::after{box-sizing:border-box}
*{margin:0}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:96px}
body{background:var(--bg);color:var(--text);font:400 15px/1.55 var(--bfont);-webkit-font-smoothing:antialiased;min-height:100vh;
  background-image:radial-gradient(1100px 520px at 88% -8%,var(--glow),transparent 62%),radial-gradient(700px 420px at -10% 8%,var(--soft),transparent 60%);background-repeat:no-repeat}
a{color:inherit;text-decoration:none}
img{display:block;max-width:100%}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
h1,h2,h3,h4{font-family:var(--hfont);font-weight:var(--hw);letter-spacing:.005em;line-height:1.02}
:focus-visible{outline:2px solid var(--accent2);outline-offset:3px;border-radius:10px}
.wrap{width:100%;max-width:1200px;margin:0 auto;padding:0 28px}
.top{position:sticky;top:0;z-index:20;background:var(--bg);background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:saturate(1.4) blur(14px);-webkit-backdrop-filter:saturate(1.4) blur(14px);border-bottom:1px solid var(--line)}
.top-in{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:68px}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.brand img{height:30px;width:auto}
.mono{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--fill);color:var(--on-fill);font:var(--hw) 18px/1 var(--hfont)}
.prod{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);white-space:nowrap;padding-left:12px;border-left:1px solid var(--line2)}
.tabs{display:flex;gap:4px;padding:4px;border-radius:999px;background:var(--surface);border:1px solid var(--line);overflow-x:auto;scrollbar-width:none;max-width:100%}
.tabs::-webkit-scrollbar{display:none}
.tabs button{padding:8px 16px;border-radius:999px;font-size:14px;font-weight:500;color:var(--muted);white-space:nowrap;transition:color .2s,background .2s}
.tabs button:hover{color:var(--text)}
.tabs .s{display:none}
.tabs button[aria-selected=true]{background:var(--text);color:var(--bg)}
.hero{padding-top:64px;padding-bottom:36px}
.eyebrow{display:inline-flex;align-items:center;gap:10px;font-size:13px;color:var(--muted);letter-spacing:.02em}
.eyebrow .dot{width:8px;height:8px;border-radius:50%;background:var(--accent2);box-shadow:0 0 0 4px var(--soft)}
.name{font-size:clamp(46px,8vw,104px);margin:14px 0 10px;overflow-wrap:anywhere}
.subline{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);font-size:16px}
.subline b{color:var(--text);font-weight:600}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:40px}
.stat{position:relative;padding:24px 24px 22px;border-radius:22px;background:var(--surface);border:1px solid var(--line);overflow:hidden;min-width:0}
.stat.hl{background:linear-gradient(160deg,var(--soft),transparent 70%),var(--surface);border-color:var(--line2)}
.stat .num{font:var(--hw) clamp(44px,5.4vw,68px)/1 var(--hfont);letter-spacing:.005em;font-variant-numeric:tabular-nums}
.stat.hl .num{color:var(--accent2)}
.stat .lbl{margin-top:10px;font-weight:600;font-size:15px}
.stat .sub{margin-top:4px;color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.stat .sub a{text-decoration:underline;text-decoration-color:var(--line2);text-underline-offset:3px}
main{padding-bottom:80px}
.panel{padding-top:28px}
.panel[hidden]{display:none}
.sec-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px 32px;flex-wrap:wrap;margin-bottom:26px}
.sec-head h2{font-size:clamp(34px,4.4vw,52px)}
.sec-head p{color:var(--muted);margin-top:8px;max-width:620px}
.sub-head{margin:44px 0 16px}
.sub-head h3{font-size:clamp(24px,2.6vw,30px)}
.sub-head p{color:var(--muted);margin-top:4px;font-size:14px}
.seg{display:flex;flex-wrap:wrap;gap:6px}
.seg button,.chip{padding:8px 14px;border-radius:999px;border:1px solid var(--line2);font-size:13.5px;font-weight:500;color:var(--muted);transition:all .2s;white-space:nowrap}
.seg button span,.chip span{opacity:.6;margin-left:4px;font-variant-numeric:tabular-nums}
.seg button:hover,.chip:hover{color:var(--text);border-color:var(--text)}
.seg button.on,.chip.on{background:var(--fill);border-color:var(--fill);color:var(--on-fill)}
.seg button.on span,.chip.on span{opacity:.8}
.pulse{margin:0 0 28px;padding:20px 22px 16px;border-radius:22px;background:var(--surface);border:1px solid var(--line)}
.pulse figcaption{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted);margin-bottom:14px}
.pl{display:inline-flex;flex-wrap:wrap;align-items:center;gap:4px 14px}
.pl>span{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px}
.sw.win{background:var(--accent2)}.sw.weak{background:var(--line2)}
.sw.line{width:16px;height:0;border-radius:0;border-top:1px dashed var(--muted)}
.pchart{position:relative;height:150px;display:flex;align-items:stretch;gap:4px}
.mid-line{position:absolute;left:0;right:0;top:calc(var(--up)*100%);border-top:1px dashed var(--line2);pointer-events:none}
.mid-line span{position:absolute;right:0;top:-22px;font-size:11.5px;color:var(--muted);background:var(--surface);padding:0 0 0 8px}
.pb{flex:1 1 0;min-width:3px;max-width:96px;position:relative;display:block}
.pb i{position:absolute;left:0;right:0;border-radius:5px;background:var(--line2);transition:filter .2s}
.pb i.u{bottom:calc((1 - var(--up))*100%);height:calc(var(--h)*var(--up))}
.pb i.d{top:calc(var(--up)*100%);height:calc(var(--h)*var(--dn))}
.pb.win i{background:linear-gradient(180deg,var(--accent2),var(--accent))}
.pb.mid i{background:color-mix(in srgb,var(--accent2) 40%,var(--line2))}
.pb:hover i{filter:brightness(1.25)}
.pcap{margin-top:10px;font-size:12.5px;color:var(--muted)}
.grid.reels{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:16px}
.card{position:relative;display:flex;flex-direction:column;border-radius:20px;background:var(--surface);border:1px solid var(--line);overflow:hidden;cursor:pointer;transition:transform .25s cubic-bezier(.2,.7,.2,1),border-color .25s,box-shadow .25s;min-width:0}
.card:hover{transform:translateY(-3px);border-color:var(--line2);box-shadow:0 18px 40px -18px var(--shade)}
.card[hidden],.is-more.is-hidden{display:none}
.thumb{position:relative;aspect-ratio:4/5;background:var(--surface2);overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:cover;object-position:50% 30%;transition:transform .6s cubic-bezier(.2,.7,.2,1)}
.card:hover .thumb img{transform:scale(1.04)}
.thumb::after{content:"";position:absolute;inset:auto 0 0 0;height:45%;background:linear-gradient(180deg,transparent,rgba(0,0,0,.55));pointer-events:none}
.noimg{width:100%;height:100%;display:grid;place-content:center;justify-items:center;gap:6px;background:radial-gradient(circle at 30% 20%,var(--soft),transparent 70%),var(--surface2)}
.noimg span{font:var(--hw) 54px/1 var(--hfont);color:var(--muted)}
.noimg small{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.badge{position:absolute;left:12px;bottom:12px;z-index:2;display:inline-flex;align-items:baseline;gap:5px;padding:7px 11px;border-radius:999px;font-weight:700;font-size:15px;line-height:1;font-variant-numeric:tabular-nums;background:rgba(12,12,12,.62);color:#fff;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.badge em{font-style:normal;font-weight:500;font-size:12px;opacity:.85}
.badge.win{background:var(--fill);color:var(--on-fill)}
.badge.off{background:rgba(60,60,60,.7)}
.rank{position:absolute;right:12px;top:10px;z-index:2;font:var(--hw) 30px/1 var(--hfont);color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.5)}
.c-body{display:flex;flex-direction:column;gap:6px;padding:16px 16px 14px;flex:1;min-width:0}
.k{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.hook{font-weight:600;font-size:15.5px;line-height:1.42;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.cap{color:var(--muted);font-size:13.5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.meta{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12.5px;color:var(--muted);margin-top:auto;padding-top:8px;font-variant-numeric:tabular-nums}
.c-foot{display:flex;justify-content:space-between;align-items:center;gap:8px;padding-top:12px;margin-top:4px;border-top:1px solid var(--line);font-size:13px;font-weight:600}
.more-link{color:var(--accent2)}
.ext{color:var(--muted);font-weight:500;font-size:13px;transition:color .2s;white-space:nowrap}
.ext:hover{color:var(--text)}
.flags{display:flex;flex-wrap:wrap;gap:6px}
.flag{font-size:11.5px;font-weight:600;padding:4px 9px;border-radius:999px;background:var(--soft);color:var(--accent2)}
.flag.grey{background:var(--line);color:var(--muted)}
.card.is-off .thumb img{filter:grayscale(1) contrast(.9);opacity:.55}
.card.is-off .hook{color:var(--muted)}
.more{display:block;margin:18px auto 0;padding:10px 20px;border-radius:999px;border:1px solid var(--line2);font-size:14px;font-weight:500}
.more:hover{border-color:var(--text)}
.empty{padding:28px;border-radius:20px;border:1px dashed var(--line2);background:color-mix(in srgb,var(--surface) 55%,transparent);max-width:680px}
.empty .e-title{font-weight:600;font-size:16px;margin-bottom:4px}
.empty p{color:var(--muted);font-size:14px}
.say{display:inline-flex;align-items:center;gap:10px;margin-top:14px;padding:8px 8px 8px 14px;border-radius:999px;background:var(--surface);border:1px solid var(--line2);color:var(--text)!important}
.say span{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.say b{font-weight:600;padding:5px 12px;border-radius:999px;background:var(--fill);color:var(--on-fill);font-size:13.5px;overflow-wrap:anywhere}
.openers{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}
.opener{display:flex;align-items:center;gap:16px;padding:12px 16px 12px 12px;border-radius:18px;background:var(--surface);border:1px solid var(--line);cursor:pointer;transition:border-color .2s;min-width:0}
.opener:hover{border-color:var(--line2)}
.o-thumb{flex:0 0 64px;height:86px;border-radius:12px;overflow:hidden;background:var(--surface2)}
.o-thumb img,.o-thumb .noimg{width:100%;height:100%;object-fit:cover}
.o-thumb .noimg span{font-size:26px}.o-thumb .noimg small{display:none}
.o-body{flex:1;min-width:0}
.o-body .hook{-webkit-line-clamp:3;font-size:15px}
.o-body .meta{padding-top:6px}
.xnum{color:var(--accent2);font-weight:700}
.opener .ext{font-size:18px;align-self:flex-start}
.lean{list-style:none;padding:0;display:grid;gap:10px;max-width:900px}
.lean li{padding:14px 18px;border-radius:16px;background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent2);font-size:14px;color:var(--muted)}
.lean .ln{color:var(--text);font-weight:600;font-size:15px}
.lean .ls{margin-top:2px;color:var(--accent2);font-weight:500}
.lean .lq{margin-top:6px;font-style:italic;overflow-wrap:anywhere}
.lean li.weak{border-left-color:var(--line2)}
.lean li.weak .ls{color:var(--muted)}
.bank-tools{display:flex;flex-direction:column;gap:14px;margin-bottom:18px}
.search{display:flex;align-items:center;gap:10px;max-width:520px;padding:0 16px;border-radius:999px;background:var(--surface);border:1px solid var(--line2)}
.search:focus-within{border-color:var(--accent2)}
.search svg{width:18px;height:18px;flex:0 0 18px;fill:none;stroke:var(--muted);stroke-width:2;stroke-linecap:round}
.search input{flex:1;min-width:0;padding:13px 0;background:none;border:0;outline:0;color:var(--text);font:inherit;font-size:15px}
.search input::placeholder{color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.bank{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}
.hookcard{display:flex;flex-direction:column;gap:12px;padding:22px;border-radius:20px;background:var(--surface);border:1px solid var(--line);min-width:0}
.hookcard[hidden]{display:none}
.h-top{display:flex;flex-wrap:wrap;gap:6px}
.tag{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:999px;background:var(--soft);color:var(--accent2)}
.tag.ghost{background:none;border:1px solid var(--line2);color:var(--muted);font-weight:500}
.tpl{font-size:18px;font-weight:600;line-height:1.45;overflow-wrap:anywhere}
.slot{color:var(--accent2);background:var(--soft);padding:0 4px;border-radius:5px;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.orig,.why{font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.orig span,.why span{display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:3px;opacity:.85}
.orig{padding-left:12px;border-left:2px solid var(--line2);font-style:italic}
.orig span{font-style:normal}
.h-foot{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin-top:auto;padding-top:12px;border-top:1px solid var(--line);font-size:13px}
.who{font-weight:600}
.who.self{color:var(--accent2)}
.hx{color:var(--muted)}.hx b{color:var(--text)}
.h-foot .ext{margin-left:auto}
.comp{margin-top:22px;padding:24px;border-radius:26px;border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 45%,transparent)}
.comp-head{display:flex;align-items:center;gap:16px;margin-bottom:20px;min-width:0}
.avatar{flex:0 0 52px;height:52px;border-radius:16px;display:grid;place-items:center;background:var(--fill);color:var(--on-fill);font:var(--hw) 26px/1 var(--hfont)}
.ch-txt{flex:1;min-width:0}
.ch-txt h3{font-size:clamp(24px,2.6vw,32px);overflow-wrap:anywhere}
.ch-txt p{display:flex;flex-wrap:wrap;gap:2px 14px;color:var(--muted);font-size:14px;margin-top:4px}
.ch-txt p b{color:var(--text);font-weight:600}
.ghost-btn{padding:9px 16px;border-radius:999px;border:1px solid var(--line2);font-size:13.5px;font-weight:500;white-space:nowrap}
.ghost-btn:hover{border-color:var(--text)}
.pillars{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.pillar{padding:20px;border-radius:18px;background:var(--surface);border:1px solid var(--line)}
.pn{font:var(--hw) 28px/1 var(--hfont);color:var(--accent2)}
.pt{font-weight:600;margin-top:10px}
.pd{color:var(--muted);font-size:14px;margin-top:4px}
.tcols{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:8px 36px}
.rgroup{margin-bottom:22px}
.rgroup h4{font-family:var(--bfont);font-weight:600;font-size:15px;display:flex;align-items:baseline;gap:10px;padding-bottom:10px;border-bottom:1px solid var(--line)}
.rgroup h4 span{font-weight:400;font-size:13px;color:var(--muted)}
.thread{display:flex;gap:14px;padding:16px 0;border-bottom:1px solid var(--line)}
.t-rank{flex:0 0 38px;font:var(--hw) 22px/1.1 var(--hfont);color:var(--muted)}
.t-body{min-width:0;flex:1}
.t-title{font-weight:600;font-size:15.5px;line-height:1.4;overflow-wrap:anywhere}
.t-title:hover{text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--line2)}
.t-text{color:var(--muted);font-size:14px;margin-top:6px;overflow-wrap:anywhere}
.t-coms{margin-top:10px;display:grid;gap:6px}
.t-coms blockquote{font-size:13.5px;padding:8px 12px;border-radius:12px;background:var(--surface);border:1px solid var(--line);overflow-wrap:anywhere}
.t-meta{font-size:12.5px;color:var(--muted);margin-top:8px}
.xlist{display:grid;gap:10px}
.xpost{padding:16px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--line);min-width:0}
.x-top{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:13px;color:var(--muted);margin-bottom:8px}
.x-top b{color:var(--text)}
.x-text{font-size:14.5px;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:10px}
dialog{margin:auto;padding:0;border:0;background:transparent;color:var(--text);max-width:min(980px,calc(100vw - 32px));width:100%;max-height:calc(100dvh - 48px)}
dialog::backdrop{background:rgba(0,0,0,.62);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.dlg-in{position:relative;background:var(--surface);border:1px solid var(--line2);border-radius:26px;max-height:calc(100dvh - 48px);overflow:auto;box-shadow:0 40px 120px -30px rgba(0,0,0,.6)}
.x-close{position:sticky;top:12px;margin:12px 12px -52px auto;z-index:3;width:40px;height:40px;border-radius:50%;background:var(--surface2);border:1px solid var(--line2);font-size:22px;line-height:1;display:grid;place-items:center}
.x-close:hover{border-color:var(--text)}
.d-grid{display:grid;grid-template-columns:280px minmax(0,1fr);gap:28px;padding:28px}
.d-media{border-radius:18px;overflow:hidden;background:var(--surface2);aspect-ratio:9/16;align-self:start;position:sticky;top:28px}
.d-media img,.d-media .noimg{width:100%;height:100%;object-fit:cover}
.d-info{min-width:0}
.d-eyebrow{font-size:13px;color:var(--muted);padding-right:44px}
.d-x{font-size:18px;margin-top:6px}
.d-x b{font:var(--hw) 54px/1 var(--hfont);color:var(--accent2);margin-right:6px}
.d-note{margin-top:10px;padding:10px 14px;border-radius:12px;background:var(--line);font-size:13.5px;color:var(--muted)}
.d-stats{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.d-stats span{padding:8px 12px;border-radius:12px;background:var(--surface2);border:1px solid var(--line);font-size:12.5px;color:var(--muted)}
.d-stats b{display:block;color:var(--text);font-size:16px;font-variant-numeric:tabular-nums}
.btn{display:inline-flex;align-items:center;gap:8px;padding:11px 18px;border-radius:999px;background:var(--fill);color:var(--on-fill);font-weight:600;font-size:14px}
.btn:hover{filter:brightness(1.08)}
.d-info h4{font-family:var(--bfont);font-weight:600;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:28px 0 10px}
.hint{font-size:12.5px;color:var(--muted);margin:-4px 0 10px}
.transcript{display:grid;gap:2px}
.tline{display:grid;grid-template-columns:44px minmax(0,1fr);gap:10px;padding:6px 10px;border-radius:10px;font-size:15px;line-height:1.55}
.tline .ts{font-size:12px;color:var(--muted);padding-top:3px;font-variant-numeric:tabular-nums}
.tline.is-hook{background:var(--soft)}
.tline.is-hook .ts{color:var(--accent2)}
.d-cap{font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.d-coms{list-style:none;padding:0;display:grid;gap:8px}
.d-coms li{font-size:14px;padding:10px 14px;border-radius:12px;background:var(--surface2);overflow-wrap:anywhere}
.foot{border-top:1px solid var(--line);padding:28px 0 40px;color:var(--muted);font-size:13px}
.foot .wrap{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 24px}
@media (max-width:900px){
  .tcols{grid-template-columns:minmax(0,1fr)}
  .openers{grid-template-columns:minmax(0,1fr)}
  .bank{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:720px){
  .wrap{padding:0 16px}
  .top-in{flex-direction:column;align-items:stretch;gap:10px;padding-top:12px;padding-bottom:12px;min-height:0}
  .tabs{align-self:stretch}
  .tabs button{flex:1 0 auto;padding:8px 10px;font-size:13.5px}
  .tabs .l{display:none}
  .tabs .s{display:inline}
  .hero{padding-top:36px;padding-bottom:18px}
  .stats{grid-template-columns:minmax(0,1fr);gap:10px;margin-top:28px}
  .stat{display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:18px;align-items:center;padding:18px}
  .stat .num{grid-row:span 2;font-size:44px;min-width:92px}
  .stat .lbl{margin-top:0}
  .grid.reels{grid-template-columns:minmax(0,1fr);gap:12px}
  .card{flex-direction:row;border-radius:18px}
  .card:hover{transform:none}
  .thumb{flex:0 0 116px;aspect-ratio:auto;min-height:190px}
  .thumb img{position:absolute;inset:0}
  .badge{left:8px;bottom:8px;padding:6px 9px;font-size:13px;flex-direction:column;gap:2px;align-items:flex-start;border-radius:12px}
  .badge em{font-size:10.5px}
  .rank{font-size:24px;right:auto;left:10px;top:8px}
  .c-body{padding:14px 14px 12px}
  .hook{font-size:14.5px}
  .comp{padding:22px 0 0;border:0;border-top:1px solid var(--line);border-radius:0;background:none;margin-top:28px}
  .c-foot{font-size:12.5px}
  .more-link,.ext{white-space:nowrap}
  .comp-head{flex-wrap:wrap}
  .avatar{flex-basis:44px;height:44px;font-size:22px;border-radius:14px}
  .ghost-btn{display:none}
  .pchart{height:120px;gap:3px}
  .mid-line span{display:none}
  .d-grid{grid-template-columns:minmax(0,1fr);padding:20px;gap:18px}
  .d-media{position:relative;top:0;max-width:150px;aspect-ratio:9/16}
  .d-x b{font-size:44px}
  .hookcard{padding:18px}
  .tpl{font-size:16.5px}
  .say{flex-wrap:wrap;border-radius:18px}
  dialog{max-width:calc(100vw - 20px);max-height:calc(100dvh - 20px)}
  .dlg-in{max-height:calc(100dvh - 20px);border-radius:22px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

JS = r"""
(function(){
  var tabs=[].slice.call(document.querySelectorAll('[data-tab]')), panels=[].slice.call(document.querySelectorAll('[data-panel]'));
  function show(id,push){
    if(!panels.some(function(p){return p.dataset.panel===id})) id=panels[0]&&panels[0].dataset.panel;
    panels.forEach(function(p){p.hidden=p.dataset.panel!==id});
    tabs.forEach(function(t){t.setAttribute('aria-selected',t.dataset.tab===id?'true':'false')});
    if(push&&history.replaceState) history.replaceState(null,'','#'+id);
  }
  tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.tab,true);var m=document.querySelector('main');if(window.scrollY>m.offsetTop)window.scrollTo({top:m.offsetTop-80})})});
  show((location.hash||'').slice(1),false);
  document.querySelectorAll('.is-more').forEach(function(e){e.classList.add('is-hidden')});
  document.addEventListener('click',function(ev){
    var b=ev.target.closest('[data-more]'); if(!b) return;
    b.parentElement.querySelectorAll('.is-more').forEach(function(e){e.classList.remove('is-hidden')});
    b.remove();
  });
  var grid=document.getElementById('my-grid');
  document.querySelectorAll('.seg [data-filter]').forEach(function(btn){
    btn.addEventListener('click',function(){
      var f=btn.dataset.filter, n=0;
      btn.parentElement.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===btn)});
      if(!grid) return;
      grid.querySelectorAll('.card').forEach(function(c){var ok=f==='all'||c.dataset.group===f;c.hidden=!ok;if(ok)n++});
      var e=grid.parentElement.querySelector('.filter-empty'); if(e) e.hidden=n>0;
    });
  });
  var q=document.getElementById('hook-q'), mech='';
  function filt(){
    var s=(q&&q.value||'').trim().toLowerCase(), n=0;
    document.querySelectorAll('.hookcard').forEach(function(c){
      var ok=(!s||c.dataset.text.indexOf(s)>-1)&&(!mech||c.dataset.mechs.split('|').indexOf(mech)>-1);
      c.hidden=!ok; if(ok) n++;
    });
    var e=document.querySelector('.bank-empty'); if(e) e.hidden=n>0;
  }
  if(q) q.addEventListener('input',filt);
  document.querySelectorAll('.chip').forEach(function(c){c.addEventListener('click',function(){
    mech=c.dataset.mech; document.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('on',x===c)}); filt();
  })});
  var dlg=document.getElementById('dlg'), body=document.getElementById('dlg-body'), last=null;
  function open(id,from){
    var t=document.getElementById(id); if(!t||!dlg) return;
    body.innerHTML=''; body.appendChild(t.content.cloneNode(true)); last=from;
    if(dlg.showModal){dlg.showModal()}else{dlg.setAttribute('open','')}
    var s=dlg.querySelector('.dlg-in'); if(s) s.scrollTop=0;
  }
  function close(){ if(dlg.close){dlg.close()}else{dlg.removeAttribute('open')} }
  if(dlg){
    dlg.addEventListener('click',function(e){if(e.target===dlg) close()});
    dlg.addEventListener('close',function(){if(last) last.focus()});
    dlg.querySelector('.x-close').addEventListener('click',close);
  }
  document.addEventListener('click',function(e){
    if(e.target.closest('a')||e.target.closest('dialog')) return;
    var c=e.target.closest('[data-open]'); if(c) open(c.dataset.open,c);
  });
  document.addEventListener('keydown',function(e){
    if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('[data-open]')){e.preventDefault();open(e.target.dataset.open,e.target)}
  });
})();
"""


def research_day(libs, dates):
    days = []
    for d in libs.values():
        try:
            days.append(dt.date.fromisoformat(str(d.get('updated', ''))[:10]))
        except Exception:
            pass
    for s in dates:
        try:
            days.append(dt.date.fromisoformat(s))
        except Exception:
            pass
    return max(days) if days else None


def about_name():
    m = re.search(r'^name:\s*(.+)$', read_text(os.path.join(ST, 'about.md')), re.M)
    return m.group(1).strip() if m else ''


def build():
    br = load_brand()
    prof = read_json(os.path.join(ST, 'profile.json'), {}) or {}
    own = (prof.get('handle') or '').lower()
    libs = load_libraries()
    od = libs.get(own)
    comps = [c for c in (prof.get('competitors') or []) if c and c != own]
    extra = [h for h, d in libs.items() if h != own and h not in comps and len(d['reels']) >= 8]
    comps += extra
    bank = parse_hook_bank()
    voice = read_text(os.path.join(ST, 'voice.md'))
    reddit, rdate = latest_radar('reddit')
    xs, xdate = latest_radar('x')

    # every picture the page shows
    jobs = []
    if od:
        jobs += [image_job(own, r) for r in od['reels']]
    for h in comps:
        d = libs.get(h)
        if d:
            jobs += [image_job(h, r) for r in d['reels'] if (r.get('x') or 0) >= 2 and (counts(r) or r.get('fresh'))]
    imgs = prepare_images([j for j in jobs if j])
    logo = copy_logo(br['logo'])

    pg = Page()
    p_my = section_my_reels(pg, own, od, imgs)
    p_hooks = section_hooks(pg, own, od, imgs, bank, voice)
    p_comp = section_competitors(pg, comps, libs, imgs)
    p_topics = section_topics(voice, reddit, rdate, xs, xdate)

    name = br['name'] or about_name() or prof.get('name') or ('@' + own if own else 'Your research')
    day = research_day(libs, [d for d in (rdate, xdate) if d])
    settled = sorted([r for r in (od or {}).get('reels', []) if counts(r) and not r.get('suspect')], key=lambda r: r['x'], reverse=True)
    best = settled[0] if settled else None
    n_reels = sum(len(d['reels']) for d in libs.values())
    n_tr = sum(1 for d in libs.values() for r in d['reels'] if r.get('transcribed'))
    n_comp = len([h for h in comps if h in libs])

    tiles = []
    if od:
        tiles.append('<div class="stat"><p class="num">%s</p><p class="lbl">views on your usual reel</p><p class="sub">The middle of your %d settled reels</p></div>' % (
            esc(fmt_n(od.get('median_views'))), len(settled)))
    else:
        tiles.append('<div class="stat"><p class="num">0</p><p class="lbl">views on your usual reel</p><p class="sub">Shows up after your first research run</p></div>')
    if best:
        tiles.append('<div class="stat hl"><p class="num">%s</p><p class="lbl">your best reel vs your usual</p><p class="sub"><a href="%s" target="_blank" rel="noopener">%s views, posted %s</a></p></div>' % (
            esc(fmt_x(best['x'])), esc(best.get('url', '#')), esc(fmt_n(best['views'])), esc(fmt_date(best.get('posted')))))
    else:
        tiles.append('<div class="stat hl"><p class="num">0x</p><p class="lbl">your best reel vs your usual</p><p class="sub">Shows up after your first research run</p></div>')
    tiles.append('<div class="stat"><p class="num">%s</p><p class="lbl">reels studied</p><p class="sub">Yours and %d competitor%s, %d transcribed</p></div>' % (
        esc(n_reels), n_comp, '' if n_comp == 1 else 's', n_tr))

    brand_html = ('<img src="%s" alt="%s">' % (esc(logo), esc(name))) if logo else '<span class="mono">%s</span>' % esc((name.lstrip('@') or 'S')[:1].upper())
    tabs = [('reels', 'My reels', 'My reels'), ('hooks', 'My hook library', 'Hooks'), ('competitors', 'Competitors', 'Competitors'), ('topics', 'Topics', 'Topics')]
    fonts = ''.join('<link rel="stylesheet" href="%s">' % esc(u) for u in br['links'])
    pre = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' if fonts else ''
    sub = []
    if own:
        sub.append('<b>@%s</b>' % esc(own))
    if prof.get('niche'):
        sub.append('<span>%s</span>' % esc(prof['niche']))
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s · Research</title><meta name="color-scheme" content="%s">%s%s<style>%s%s</style></head><body>'
        '<header class="top"><div class="wrap top-in"><div class="brand">%s<span class="prod">Script Studio</span></div>'
        '<nav class="tabs" role="tablist" aria-label="Sections">%s</nav></div></header>'
        '<section class="hero wrap"><p class="eyebrow"><span class="dot"></span>%s</p><h1 class="name">%s</h1>'
        '<p class="subline">%s</p><div class="stats">%s</div></section>'
        '<main class="wrap">'
        '<section class="panel" data-panel="reels" aria-label="My reels">%s</section>'
        '<section class="panel" data-panel="hooks" aria-label="My hook library">%s</section>'
        '<section class="panel" data-panel="competitors" aria-label="Competitors">%s</section>'
        '<section class="panel" data-panel="topics" aria-label="Topics">%s</section>'
        '</main>'
        '<footer class="foot"><div class="wrap"><span>Built by Script Studio on %s.</span><span>Fresh numbers after every research refresh. Say "refresh my research".</span></div></footer>'
        '<dialog id="dlg" aria-label="Reel details"><div class="dlg-in"><button class="x-close" aria-label="Close">×</button><div id="dlg-body"></div></div></dialog>'
        '%s<script>%s</script></body></html>') % (
        esc(name), 'light' if br['light'] else 'dark', pre, fonts, css_vars(br), CSS, brand_html,
        ''.join('<button role="tab" data-tab="%s" aria-selected="false"><span class="l">%s</span><span class="s">%s</span></button>' % t for t in tabs),
        esc(('Research updated %s · %s' % (fmt_date(day, True), ago(day))) if day else 'No research yet'),
        esc(name), ' '.join(sub), ''.join(tiles), p_my, p_hooks, p_comp, p_topics,
        esc(fmt_date(dt.date.today().isoformat(), True)), ''.join(pg.templates), JS)
    page = re.sub('\\s*\u2014\\s*', ', ', page)   # never an em dash anywhere on the page
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, 'index.html')
    with open(path + '.tmp', 'w', encoding='utf-8') as fh:
        fh.write(page)
    os.replace(path + '.tmp', path)
    return path


def open_file(path):
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform.startswith('win'):
            os.startfile(path)   # noqa
        else:
            subprocess.Popen(['xdg-open', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog='dashboard.py', description='Build the Script Studio research dashboard.')
    ap.add_argument('--open', action='store_true', help='open it in the default browser')
    a = ap.parse_args()
    path = build()
    if a.open:
        open_file(path)
    print('DASHBOARD %s' % path)


if __name__ == '__main__':
    main()
