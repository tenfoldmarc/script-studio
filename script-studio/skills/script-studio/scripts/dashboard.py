#!/usr/bin/env python3
"""Script Studio dashboard: the buyer's research on one page, in their own branding.

  PY dashboard.py [--open] [--rebuild]

Reads the buyer's Script Studio folder (env SCRIPT_STUDIO_STATE, else the per-OS data folder for 'script-studio',
the same folder ss.py uses) and writes into <state>/dashboard/:
  index.html  the fixed shell: layout, brand styles, and the JS that renders every tab, filter, search and dialog.
              Written only when missing, when brand.json (or the logo, or this template) changed, or with --rebuild.
  data.js     window.SS_DATA, everything the page shows. Rewritten on every run (temp file + rename). An open page
              loads it again every 20 s and re-renders in place, so a refresh never needs the page reopened.
  img/        the reel pictures. Only new ones are copied or downloaded (shrunk to 540px JPEG with the Creator
              Studio's ffmpeg when it is installed); pictures the page no longer shows are removed.
Prints DASHBOARD <path>, then BUILT shell+data or UPDATED data. --open opens it in the default browser.
Standard library only, Python 3.9+. Never writes outside <state>/dashboard/.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
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


TAGS = re.compile(r'\s*\[(inferred|confirmed|likely)[^\]]*\]', re.I)
FILE_REFS = re.compile(r'[,;]?\s*(\(\s*)?\b((from|see|in|per|via)\s+)?(ST/)?(about|voice|taste|hook-bank)\.md\b(\s*\))?', re.I)


def clean_note(s):
    """A voice.md line without its [inferred]/[confirmed] tags or mentions of the buyer's files."""
    s = FILE_REFS.sub('', TAGS.sub('', s or ''))
    return re.sub(r'\s{2,}', ' ', s).strip().strip(',;').strip()


def parse_pillar(s):
    """[title, body, proof url, proof label] from '<pillar>: <line> | proof: <URL>, <x>x [tag]'."""
    parts = [p.strip() for p in TAGS.sub('', s).split(' | ')]
    main, url, label = parts[0], '', ''
    for p in parts[1:]:
        if p.lower().startswith('proof'):
            m = re.search(r'https?://[^\s,]+', p)
            url = m.group(0) if m else ''
            mx = re.search(r'(\d+(?:\.\d+)?)\s*x\b', p[m.end():] if m else p)
            if mx:
                label = 'Proof: %sx' % ('%d' % round(float(mx.group(1))) if float(mx.group(1)) >= 10 else
                                        ('%.1f' % float(mx.group(1))).rstrip('0').rstrip('.'))
            elif url:
                label = 'Proof'
        else:
            main += ' ' + p
    main = clean_note(main)
    title, body = main.strip('*'), ''
    if ': ' in main:
        a, b = main.split(': ', 1)
        if len(a) <= 90:
            title, body = a.strip().strip('*'), b.strip()
    return [title, body, url, label]


def norm_q(s):
    return (s or '').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"').lower()


ALWAYS_BANNED = ('selling a course', 'selling of course')


def banned_phrases(about, voice):
    """Phrases the buyer never says: quoted ones in their rules, plus the short rule text itself."""
    lines = bullets(md_sections(about).get('never do or say', []))
    for k, v in md_sections(voice).items():
        if k.startswith('hard rules'):
            lines += bullets(v)
    out = set(ALWAYS_BANNED)
    for ln in lines:
        ln = norm_q(TAGS.sub('', ln))
        quoted = re.findall(r'"([^"]{3,})"', ln)
        out.update(q.strip(' .,!?') for q in quoted if len(q.strip(' .,!?')) >= 4)
        neg = re.match(r'^(no|never|don\'t|do not|avoid|banned:?)\s+((say|use|do|trash)\s+)?', ln.strip())
        if not quoted and neg:
            rest = re.split(r'[,.;:(]', ln.strip()[neg.end():])[0].strip()
            if len(rest.split()) >= 2:
                out.add(rest)
    return sorted(p for p in out if p)


def is_banned(line, banned):
    t = norm_q(line)
    return any(p in t for p in banned)


def voice_openers(voice):
    """(quote, x) for each line of voice.md's Openers section."""
    out = []
    for b in bullets(md_sections(voice).get('openers', [])):
        b = b.replace('“', '"').replace('”', '"')
        head = b.split(' | ')[0].strip()
        m = re.match(r'^"(.+?)"', head)
        quote = m.group(1).strip() if m else clean_note(head).strip('"')
        mx = re.search(r'(\d+(?:\.\d+)?)\s*x\b', b.split(' | ')[-1]) if ' | ' in b else None
        if quote:
            out.append((quote, float(mx.group(1)) if mx else None))
    return out


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
THUMB_W = 540


def find_ffmpeg():
    """The Creator Studio's ffmpeg, when it is installed. None otherwise: images are then kept as they come."""
    cfg = read_json(os.path.join(data_dir('video-studio'), '.platform.json'), {}) or {}
    f = cfg.get('ffmpeg') if isinstance(cfg, dict) else None
    return f if isinstance(f, str) and os.path.isfile(f) else None


FFMPEG = None


def shrink(src, dest):
    """A 540px wide JPEG of src at dest. False (and nothing written) when ffmpeg is missing or fails."""
    if not FFMPEG:
        return False
    tmp = dest + '.part.jpg'
    try:
        r = subprocess.run(
            [FFMPEG, '-nostdin', '-y', '-loglevel', 'error', '-i', src, '-frames:v', '1',
             '-vf', "scale='min(%d,iw)':-2" % THUMB_W, '-q:v', '4', '-f', 'image2', '-update', '1', tmp],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40,
            creationflags=0x08000000 if sys.platform.startswith('win') else 0)
        if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, dest)
            return True
    except Exception:
        pass
    try:
        os.remove(tmp)
    except Exception:
        pass
    return False


def run_image_job(job):
    key, kind, src = job
    for ext in ('.jpg', '.png', '.webp'):
        dest = os.path.join(IMG, key + ext)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            if kind == 'get' or os.path.getmtime(dest) >= os.path.getmtime(src):
                return key, 'img/' + key + ext
    dest = os.path.join(IMG, key + '.jpg')
    try:
        if kind == 'copy':
            if not shrink(src, dest):
                shutil.copyfile(src, dest + '.part')
                os.replace(dest + '.part', dest)
            return key, 'img/' + key + '.jpg'
        req = urllib.request.Request(src, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read(6 * 1024 * 1024 + 1)
        if len(data) > 6 * 1024 * 1024:
            return key, None
        ext = next((e for m, e in MAGIC if data.startswith(m)), None)
        if not ext:
            return key, None
        raw = os.path.join(IMG, key + '.part' + ext)
        with open(raw, 'wb') as fh:
            fh.write(data)
        if shrink(raw, dest):
            os.remove(raw)
            return key, 'img/' + key + '.jpg'
        os.replace(raw, os.path.join(IMG, key + ext))
        return key, 'img/' + key + ext
    except Exception:
        return key, None


def prepare_images(jobs):
    """Copies or downloads only the pictures not in img/ yet (or older than their frame)."""
    global FFMPEG
    os.makedirs(IMG, exist_ok=True)
    uniq = {}
    for j in jobs:
        if j and j[0] not in uniq:
            uniq[j[0]] = j
    FFMPEG = find_ffmpeg()
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(run_image_job, uniq.values()))


def tidy_images(used):
    """Removes reel pictures the page no longer shows, and leftovers of interrupted writes. The logo stays."""
    keep = {os.path.basename(p) for p in used if p}
    for f in os.listdir(IMG) if os.path.isdir(IMG) else []:
        p = os.path.join(IMG, f)
        if f in keep or f.startswith('logo.') or not os.path.isfile(p):
            continue
        if '.part' in f or ('--' in f and f.lower().endswith(('.jpg', '.png', '.webp'))):
            try:
                os.remove(p)
            except Exception:
                pass


def logo_source(path):
    if not path:
        return None
    p = os.path.expanduser(path if os.path.isabs(path) else os.path.join(ST, path))
    ext = os.path.splitext(p)[1].lower()
    if not os.path.isfile(p) or ext not in ('.png', '.jpg', '.jpeg', '.svg', '.webp'):
        return None
    return p


def copy_logo(path):
    p = logo_source(path)
    if not p:
        return None
    ext = os.path.splitext(p)[1].lower()
    dest = os.path.join(IMG, 'logo' + ext)
    os.makedirs(IMG, exist_ok=True)
    try:
        if not os.path.isfile(dest) or os.path.getmtime(dest) < os.path.getmtime(p):
            shutil.copyfile(p, dest + '.part')
            os.replace(dest + '.part', dest)
        return 'img/logo' + ext
    except Exception:
        return None


# ---------- the page's data (written to data.js; the shell's JS turns it into markup) ----------

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


def reel_view(h, r, img, whose):
    """Everything the card and the dialog show for one reel, already formatted."""
    code = r.get('code') or ''
    segs = segments(h, code)
    has_tr = r.get('transcribed') or os.path.isfile(os.path.join(reel_dir(h, code), 'transcript.json'))
    # trend audio: the transcript is song lyrics, never a spoken hook
    hook = hook_line(h, code) if has_tr and r.get('original_audio') is not False else ''
    x = r.get('x') or 0
    v = {
        'h': h, 'url': r.get('url', '#'), 'img': img or '', 'whose': whose,
        'x': fmt_x(x), 'tone': 'win' if x >= 1.2 else ('weak' if x < 0.7 else 'mid'),
        'views': fmt_n(r.get('views')), 'likes': fmt_n(r.get('likes')), 'comments': fmt_n(r.get('comments')),
        'dur': fmt_len(r.get('duration')), 'posted': fmt_date(r.get('posted')), 'posted_full': fmt_date(r.get('posted'), True),
        'cap1': first_line(r.get('caption'), 160), 'cap': (r.get('caption') or '').strip(), 'hook': first_line(hook, 220),
        'segs': [[fmt_ts(s.get('start')), s['text'].strip(), 1 if (s.get('start') or 0) < 4 else 0] for s in segs],
        'text': '' if segs else transcript_text(h, code),
        'coms': [first_line(c, 300) for c in [c for c in (r.get('top_comments') or []) if good_comment(c)][:6]],
    }
    if r.get('duration'):
        v['hasdur'] = 1
    if r.get('collab'):
        v['collab'] = 1
    if 'url' not in r:
        v['nourl'] = 1
    return v


class Reels:
    """Each reel the page shows, stored once and referenced by key."""

    def __init__(self, imgs):
        self.imgs = imgs
        self.map = {}

    def key(self, h, r, whose):
        k = '%s/%s' % (h, r.get('code') or '')
        if k not in self.map:
            self.map[k] = reel_view(h, r, self.imgs.get(safe_name(h, r.get('code') or '')), whose)
        return k


def card_item(k, rank=None, label=None, group='', hide=False):
    it = {'k': k}
    if rank:
        it['rank'] = rank
    if label:
        it['label'] = list(label)
    if group:
        it['group'] = group
    if hide:
        it['hide'] = 1
    return it


def pulse_data(reels, med):
    """Every settled reel, oldest to newest, above or below the usual (log scale)."""
    import math
    rs = sorted(reels, key=lambda r: r.get('posted') or '')
    if len(rs) < 3:
        return None
    xs = [max(0.1, r['x'] or 0.1) for r in rs]
    up = max(math.log10(max(xs)), 0.3)
    dn = max(math.log10(1 / min(xs)), 0.3)
    bars = []
    for r, x in zip(rs, xs):
        v = math.log10(x)
        cls = 'win' if x >= 1.2 else ('weak' if x < 0.7 else 'mid')
        pct = abs(v) / (up if v >= 0 else dn) * 100
        bars.append([cls, r.get('url', '#'), '%s · %s views · %s your usual' % (fmt_date(r.get('posted')), fmt_n(r.get('views')), fmt_x(x)),
                     '%.1f' % max(pct, 2.5), 'u' if v >= 0 else 'd'])
    best = max(rs, key=lambda r: r['x'])
    return {'med': fmt_n(med), 'up': '%.3f' % (up / (up + dn)), 'dn': '%.3f' % (dn / (up + dn)), 'bars': bars,
            'bx': fmt_x(best['x']), 'bd': fmt_date(best.get('posted'))}


def data_my(own, od, rv):
    if not own:
        return {'state': 'noaccount'}
    if not od:
        return {'state': 'nostudy'}
    reels = od['reels']
    ranked = sorted([r for r in reels if counts(r) and not r.get('suspect')], key=lambda r: r['x'], reverse=True)
    off = [r for r in reels if not (counts(r) and not r.get('suspect'))]
    items = []
    for i, r in enumerate(ranked, 1):
        g = 'win' if r['x'] >= 1.2 else ('weak' if r['x'] < 0.7 else 'mid')
        items.append(card_item(rv.key(own, r, 'your'), rank=i, group=g))
    off.sort(key=lambda r: r.get('posted') or '', reverse=True)
    return {
        'state': 'ok',
        'n': [len(ranked), sum(1 for r in ranked if r['x'] >= 1.2), sum(1 for r in ranked if r['x'] < 0.7)],
        'pulse': pulse_data(ranked, od.get('median_views')),
        'ranked': items,
        'off': [card_item(rv.key(own, r, 'your'), label=off_label(r), hide=i >= 8) for i, r in enumerate(off)],
    }


def opener_reel(r):
    """A reel whose opening line is really the buyer's: their own voice, settled and counted."""
    return (counts(r) and not r.get('suspect') and r.get('original_audio') is not False
            and (r.get('x') or 0) >= 1.2 and bool(r.get('code')))


def winning_openers(own, od, rv, voice, banned):
    """The buyer's winning first lines: voice.md's Openers first (matched to their reel), then transcripts."""
    if not od:
        return []
    reels = sorted([r for r in od['reels'] if opener_reel(r)], key=lambda r: r['x'], reverse=True)
    wins, used = [], set()
    for quote, x in voice_openers(voice):
        if x is None or is_banned(quote, banned):
            continue
        cands = [r for r in reels if r['code'] not in used and abs(r['x'] - x) < 0.006]
        if not cands:
            continue
        q = set(norm_q(quote).split())
        r = max(cands, key=lambda r: len(q & set(norm_q(hook_line(own, r['code'])).split())))
        used.add(r['code'])
        wins.append((r['x'], {'k': rv.key(own, r, 'your'), 'hook': first_line(quote, 200)}))
    for r in reels:
        if r['code'] in used:
            continue
        hk = hook_line(own, r['code'])
        if hk and not is_banned(hk, banned):
            wins.append((r['x'], {'k': rv.key(own, r, 'your'), 'hook': first_line(hk, 200)}))
    wins.sort(key=lambda w: w[0], reverse=True)
    return [w for _, w in wins]


def data_hooks(own, od, rv, bank, voice, banned=()):
    wins = winning_openers(own, od, rv, voice, banned)
    lean = []
    for b in bullets(md_sections(voice).get('hook types they lean on', [])):
        b = re.sub(r'\bfor (him|her|them)\b', 'for you', re.sub(r'\s*\[(inferred|confirmed|likely)[^\]]*\]\s*$', '', b))
        left, _, quote = b.partition(' | ')
        name, stat = left, ''
        m = re.match(r'^(.*?\S)(?::\s+)([^:]*)$', left)
        if m and len(m.group(1)) < 140:
            name, stat = m.group(1), m.group(2)
        lean.append({'name': name, 'stat': stat, 'quote': quote, 'weak': 1 if name.lower().startswith(('weak', 'avoid', 'flop')) else 0})
    mechs = {}
    for e in bank:
        for m in e['mechs']:
            mechs[m] = mechs.get(m, 0) + 1
    cards = []
    for e in bank:
        who = 'You' if e['self'] else e['creator']
        surface = {'spoken': 'the spoken line', 'on-screen': 'the on-screen text', 'frame one': 'the first frame',
                   'caption': 'the caption'}.get(e['surface'].lower(), e['surface'])
        cards.append({
            'tpl': e['template'], 'mechs': e['mechs'], 'ml': '|'.join(m.lower() for m in e['mechs']), 'surface': surface,
            'orig': e['original'], 'why': e['why'], 'who': who, 'self': 1 if e['self'] else 0,
            'x': fmt_x(e['x']) if e['x'] else '', 'whose': 'your' if e['self'] else 'their', 'views': e['views'], 'url': e['url'],
            'text': ' '.join([e['template'], e['original'], e['why'], who, ' '.join(e['mechs'])]).lower(),
        })
    return {'wins': wins[:10], 'lean': lean, 'bank': cards,
            'chips': [[m.lower(), m, n] for m, n in sorted(mechs.items(), key=lambda kv: (-kv[1], kv[0]))]}


def data_comps(comps, libs, rv):
    out = []
    for h in comps:
        d = libs.get(h)
        if not d:
            out.append({'h': h, 'studied': 0})
            continue
        rs = d['reels']
        settled = [r for r in rs if counts(r)]
        outl = sorted([r for r in settled if r['x'] >= 2], key=lambda r: r['x'], reverse=True)
        climbing = sorted([r for r in rs if r.get('fresh') and r['x'] >= 2], key=lambda r: r['x'], reverse=True)[:3]
        best = max(settled, key=lambda r: r['x']) if settled else None
        cards = [card_item(rv.key(h, r, 'their'), rank=i, hide=i > 6) for i, r in enumerate(outl, 1)]
        cards += [card_item(rv.key(h, r, 'their'), label=off_label(r)) for r in climbing]
        out.append({'h': h, 'studied': 1, 'med': fmt_n(d.get('median_views')), 'n': len(rs),
                    'best': fmt_x(best['x']) if best else '', 'best_any': fmt_x(best['x']) if best else 'none',
                    'cards': cards, 'nout': len(outl)})
    return out


def data_topics(voice, reddit, rdate, xs, xdate):
    pillars = [p for p in (parse_pillar(b) for b in bullets(md_sections(voice).get('pillars', []))) if p[0]]
    out = {'pillars': pillars, 'reddit': None, 'x': None}
    if reddit:
        by = {}
        for it in sorted(reddit, key=lambda x: x.get('rank') or 99):
            by.setdefault(it.get('where') or 'Reddit', []).append(it)
        groups = []
        for where, items in by.items():
            groups.append({'where': where, 'items': [{
                'rank': str(it.get('rank') or i + 1), 'url': it.get('url', '#'), 'title': it.get('title') or 'Untitled',
                'text': first_line(it.get('text'), 260),
                'coms': [first_line(c, 220) for c in [c for c in (it.get('top_comments') or []) if good_comment(c)][:3]],
                'period': it.get('period') or 'week', 'posted': fmt_date(it.get('posted')) if it.get('posted') else None,
            } for i, it in enumerate(items)]})
        out['reddit'] = {'date': fmt_date(rdate) if rdate else '', 'groups': groups}
    if xs:
        out['x'] = {'date': fmt_date(xdate) if xdate else '', 'posts': [{
            'where': p.get('where') or '', 'likes': fmt_n(p.get('likes')),
            'posted': fmt_date(p.get('posted')) if p.get('posted') else None,
            'text': (p.get('text') or '').strip(), 'url': p.get('url') or '#',
        } for p in sorted(xs, key=lambda x: x.get('likes') or 0, reverse=True)]}
    return out


# ---------- the shell (index.html: written once per brand) ----------

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
.pillar{padding:20px;border-radius:18px;background:var(--surface);border:1px solid var(--line);min-width:0;overflow-wrap:anywhere}
.pn{font:var(--hw) 28px/1 var(--hfont);color:var(--accent2)}
.pt{font-weight:600;margin-top:10px}
.pd{color:var(--muted);font-size:14px;margin-top:4px}
.pproof{display:inline-block;margin-top:10px;font-size:12.5px;font-weight:600;color:var(--accent2)}
.pproof:hover{text-decoration:underline}
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
.upd{position:fixed;left:50%;bottom:22px;z-index:30;display:inline-flex;align-items:center;gap:8px;padding:9px 16px;border-radius:999px;background:var(--surface2);border:1px solid var(--line2);color:var(--text);font-size:13px;font-weight:500;box-shadow:0 18px 40px -18px var(--shade);opacity:0;transform:translate(-50%,10px);pointer-events:none;transition:opacity .3s,transform .3s}
.upd.on{opacity:1;transform:translate(-50%,0)}
.upd i{width:7px;height:7px;border-radius:50%;background:var(--accent2);box-shadow:0 0 0 3px var(--soft)}
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
  var SHELL=window.SS_SHELL||{}, R={}, DT=[], cur=null;
  var st={filter:'all',mech:'',q:'',more:{}};
  function $(id){return document.getElementById(id)}
  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;')}
  function md(s){return esc(s).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')}
  function each(a,f){return (a||[]).map(f).join('')}
  function say(cmd){return '<p class="say"><span>Say</span><b>'+esc(cmd)+'</b></p>'}
  function empty(t,b,cmd){return '<div class="empty"><p class="e-title">'+esc(t)+'</p><p>'+esc(b)+'</p>'+(cmd?say(cmd):'')+'</div>'}
  function thumb(src,h,alt){
    if(src) return '<img src="'+esc(src)+'" alt="'+esc(alt)+'" loading="lazy" decoding="async">';
    return '<div class="noimg"><span>'+esc((h||'?').charAt(0).toUpperCase())+'</span><small>No preview</small></div>';
  }
  function ext(href,label,cls){return '<a class="'+(cls||'ext')+'" href="'+esc(href)+'" target="_blank" rel="noopener">'+label+' <span aria-hidden="true">\u2197</span></a>'}
  function detail(k,note){DT.push([k,note||'']);return 'd'+DT.length}

  /* ---- the dialog: the full view of a reel ---- */
  function reelDetail(v,note){
    var tr='<h4>What was said</h4>';
    if(v.segs.length){
      tr+='<p class="hint">The highlighted lines are the first 4 seconds: the spoken hook.</p><div class="transcript">'+each(v.segs,function(s){
        return '<p class="tline'+(s[2]?' is-hook':'')+'"><span class="ts">'+esc(s[0])+'</span><span>'+esc(s[1])+'</span></p>'})+'</div>';
    }else if(v.text){
      tr+='<div class="transcript"><p>'+esc(v.text)+'</p></div>';
    }else{
      tr+=v.whose==='your'?empty('Not transcribed yet','This one gets transcribed in a later refresh once it has settled.','refresh my research')
        :empty('Not transcribed yet','Want the exact words? Ask for this reel by its link.','transcribe this reel '+(v.nourl?'':v.url));
    }
    var stats=[[v.views,'views'],[v.likes,'likes'],[v.comments,'comments']];
    if(v.hasdur) stats.push([v.dur,'long']);
    return '<div class="d-grid"><div class="d-media">'+thumb(v.img,v.h,'First frame of the reel')+'</div><div class="d-info">'+
      '<p class="d-eyebrow">@'+esc(v.h)+' \u00b7 posted '+esc(v.posted_full)+'</p>'+
      '<p class="d-x"><b>'+esc(v.x)+'</b> '+v.whose+' usual</p>'+(note?'<p class="d-note">'+esc(note)+'</p>':'')+
      '<div class="d-stats">'+each(stats,function(s){return '<span><b>'+esc(s[0])+'</b>'+esc(s[1])+'</span>'})+'</div>'+
      '<a class="btn" href="'+esc(v.url)+'" target="_blank" rel="noopener">Open the post <span aria-hidden="true">\u2197</span></a>'+tr+
      (v.cap?'<h4>Caption</h4><p class="d-cap">'+esc(v.cap).replace(/\n/g,'<br>')+'</p>':'')+
      (v.coms.length?'<h4>What people commented</h4><ul class="d-coms">'+each(v.coms,function(c){return '<li>'+esc(c)+'</li>'})+'</ul>':'')+
      '</div></div>';
  }

  /* ---- a reel card ---- */
  function card(it){
    var v=R[it.k], lab=it.label, tid=detail(it.k,lab?lab[1]:''), flags='';
    if(v.collab) flags+='<span class="flag">Collab or paid: weigh lightly</span>';
    if(lab) flags+='<span class="flag grey">'+esc(lab[0])+'</span>';
    var main=v.hook?'<p class="k">Spoken hook</p><p class="hook">\u201c'+esc(v.hook)+'\u201d</p>'
      :'<p class="k">Caption</p><p class="hook">'+esc(v.cap1||'No caption')+'</p>';
    var meta=[v.views+' views',v.posted,v.dur].filter(function(m){return m});
    return '<article class="card reel'+(lab?' is-off':'')+(it.hide?' is-more':'')+'" data-group="'+esc(it.group||'')+'" data-open="'+tid+'" tabindex="0" role="button" aria-label="Open details for this reel">'+
      '<div class="thumb">'+thumb(v.img,v.h,'Reel by @'+v.h)+'<span class="badge '+(lab?'off':v.tone)+'">'+esc(v.x)+' <em>'+v.whose+' usual</em></span>'+
      (it.rank?'<span class="rank">'+it.rank+'</span>':'')+'</div>'+
      '<div class="c-body">'+(flags?'<div class="flags">'+flags+'</div>':'')+main+((v.hook&&v.cap1)?'<p class="cap">'+esc(v.cap1)+'</p>':'')+
      '<div class="meta">'+each(meta,function(m){return '<span>'+esc(m)+'</span>'})+'</div>'+
      '<div class="c-foot"><span class="more-link">'+(v.hook?'Read transcript':'Details')+'</span>'+
      '<a href="'+esc(v.url)+'" target="_blank" rel="noopener" class="ext">Open post <span aria-hidden="true">\u2197</span></a></div>'+
      '</div></article>';
  }
  function more(key,n){return '<button class="more" data-more="'+esc(key)+'">Show all '+n+'</button>'}

  /* ---- My reels ---- */
  function pulse(p){
    if(!p) return '';
    return '<figure class="pulse"><figcaption><span>Every settled reel, oldest to newest</span>'+
      '<span class="pl"><span><i class="sw win"></i>above your usual</span><span><i class="sw weak"></i>below</span><span><i class="sw line"></i>your usual, '+esc(p.med)+' views</span></span></figcaption>'+
      '<div class="pchart" style="--up:'+p.up+';--dn:'+p.dn+'"><div class="mid-line"></div>'+each(p.bars,function(b){
        return '<a class="pb '+b[0]+'" href="'+esc(b[1])+'" target="_blank" rel="noopener" title="'+esc(b[2])+'"><i style="--h:'+b[3]+'%" class="'+b[4]+'"></i></a>'})+'</div>'+
      '<p class="pcap">Tallest bar: '+esc(p.bx)+' your usual, '+esc(p.bd)+'.</p></figure>';
  }
  function secMy(d){
    if(d.state==='noaccount') return empty('No account set up yet','Tell Claude your Instagram handle and it studies your reels for you.','set up Script Studio');
    if(d.state!=='ok') return empty('Your reels are not studied yet','Claude collects your public reels, ranks them against your own usual and transcribes the best and the weakest.','refresh my research');
    var out='<div class="sec-head"><div><h2>My reels</h2><p>Ranked by how far each one beat your usual. Tap a reel to read exactly what you said.</p></div>'+
      '<div class="seg" role="group" aria-label="Filter your reels"><button class="on" data-filter="all">All <span>'+d.n[0]+'</span></button>'+
      '<button data-filter="win">Winners, 1.2x+ <span>'+d.n[1]+'</span></button><button data-filter="weak">Weakest, under 0.7x <span>'+d.n[2]+'</span></button></div></div>';
    out+=pulse(d.pulse);
    if(d.ranked.length) out+='<div class="grid reels" id="my-grid">'+each(d.ranked,card)+'</div>'+
      '<div class="empty filter-empty" hidden><p class="e-title">Nothing in this group yet</p><p>Try another filter.</p></div>';
    else out+=empty('No settled reels yet','Reels need about 3 days before their views settle. Check back after your next refresh.','refresh my research');
    if(d.off.length) out+='<div class="sub-head"><h3>Not counted yet</h3><p>Too new, a repeat, or suspiciously low. They never count toward your usual or the ranking.</p></div>'+
      '<div class="grid reels off-grid">'+each(d.off,card)+'</div>'+(d.off.length>8?more('off',d.off.length):'');
    return out;
  }

  /* ---- My hook library ---- */
  function secHooks(d){
    var out='<div class="sec-head"><div><h2>My hook library</h2><p>Opening lines that already won, as templates you can reuse. Your own first, then the best from around you.</p></div></div>'+
      '<div class="sub-head"><h3>Your winning openers</h3><p>The first 4 seconds of your reels that beat your usual.</p></div>';
    if(d.wins.length) out+='<div class="openers">'+each(d.wins,function(w){
      var v=R[w.k];
      return '<article class="opener" data-open="'+detail(w.k,'')+'" tabindex="0" role="button"><div class="o-thumb">'+thumb(v.img,v.h,'Your reel')+'</div><div class="o-body">'+
        '<p class="hook">\u201c'+esc(w.hook)+'\u201d</p><p class="meta"><b class="xnum">'+esc(v.x)+' your usual</b><span>'+esc(v.views)+' views</span><span>'+esc(v.posted)+'</span></p></div>'+
        '<a class="ext" href="'+esc(v.url)+'" target="_blank" rel="noopener" aria-label="Open the post">\u2197</a></article>'})+'</div>';
    else out+=empty('No winning openers yet','Once a few of your reels beat your usual and get transcribed, their first lines land here.','refresh my research');
    if(d.lean.length) out+='<div class="sub-head"><h3>The hook types that work for you</h3><p>From your voice profile.</p></div><ul class="lean">'+each(d.lean,function(l){
      return '<li class="'+(l.weak?'weak':'')+'"><p class="ln">'+md(l.name)+'</p>'+(l.stat?'<p class="ls">'+md(l.stat)+'</p>':'')+(l.quote?'<p class="lq">'+md(l.quote)+'</p>':'')+'</li>'})+'</ul>';
    out+='<div class="sub-head"><h3>Hook bank</h3><p>Every saved hook, best first. The words in color are the parts you swap for your own.</p></div>';
    if(!d.bank.length) return out+empty('Your hook bank is empty','Claude fills it from the reels that beat their creator\'s usual, yours and your competitors\'.','refresh my research');
    out+='<div class="bank-tools"><label class="search"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="6"/><path d="m14 14 4 4"/></svg>'+
      '<input type="search" id="hook-q" placeholder="Search hooks, words, creators" aria-label="Search the hook bank"></label>'+
      '<div class="chips" role="group" aria-label="Filter by hook type"><button class="chip on" data-mech="">All <span>'+d.bank.length+'</span></button>'+
      each(d.chips,function(c){return '<button class="chip" data-mech="'+esc(c[0])+'">'+esc(c[1])+' <span>'+c[2]+'</span></button>'})+'</div></div>';
    out+='<div class="bank" id="bank">'+each(d.bank,function(e){
      return '<article class="hookcard" data-mechs="'+esc(e.ml)+'" data-text="'+esc(e.text)+'">'+
        '<div class="h-top">'+each(e.mechs,function(m){return '<span class="tag">'+esc(m)+'</span>'})+(e.surface?'<span class="tag ghost">Carried by '+esc(e.surface)+'</span>':'')+'</div>'+
        '<p class="tpl">'+esc(e.tpl).replace(/\[([^\]]+)\]/g,'<span class="slot">$1</span>')+'</p>'+
        '<p class="orig"><span>Original</span>'+esc(e.orig)+'</p>'+(e.why?'<p class="why"><span>Why it works</span>'+esc(e.why)+'</p>':'')+
        '<div class="h-foot"><span class="who'+(e.self?' self':'')+'">'+esc(e.who)+'</span>'+
        (e.x?'<span class="hx"><b>'+esc(e.x)+'</b> '+e.whose+' usual'+(e.views?', '+esc(e.views)+' views':'')+'</span>':'')+
        ext(e.url,'See it')+'</div></article>'})+'</div>'+
      '<div class="empty bank-empty" hidden><p class="e-title">No hook matches that</p><p>Try a shorter word or another hook type.</p></div>';
    return out;
  }

  /* ---- Competitors ---- */
  function secComp(list){
    var out='<div class="sec-head"><div><h2>Competitors</h2><p>The reels that beat their own usual by 2x or more. Their usual, not their follower count, is the bar.</p></div></div>';
    if(!list.length) return out+empty('No competitors yet','Name 3 to 10 accounts whose reels pop in your space and Claude studies them.','add a competitor');
    list.forEach(function(c){
      var head=function(sub){return '<header class="comp-head"><div class="avatar">'+esc(c.h.charAt(0).toUpperCase())+'</div><div class="ch-txt"><h3>@'+esc(c.h)+'</h3>'+sub+'</div>'+
        ext('https://www.instagram.com/'+c.h+'/','Profile','ghost-btn')+'</header>'};
      if(!c.studied){
        out+='<section class="comp">'+head('<p>Not studied yet</p>')+empty('Not studied yet','This account has not been collected. If it stays empty after a refresh, it is private or the handle is off.','refresh my research')+'</section>';
        return;
      }
      var sub='<p>Usual reel: <b>'+esc(c.med)+' views</b><span>'+c.n+' reels studied</span>'+(c.best?'<span>Best: '+esc(c.best)+'</span>':'')+'</p>';
      out+='<section class="comp">'+head(sub)+(c.cards.length?'<div class="grid reels">'+each(c.cards,card)+'</div>'
        :empty('No breakout reels right now','None of their settled reels beat their usual by 2x. Their best so far: '+c.best_any+'.'))+
        (c.nout>6?more('comp:'+c.h,c.nout):'')+'</section>';
    });
    return out;
  }

  /* ---- Topics ---- */
  function secTopics(d){
    var out='<div class="sec-head"><div><h2>Topics</h2><p>What your audience is talking about right now, and the pillars your content stands on.</p></div></div>'+
      '<div class="sub-head"><h3>Your pillars</h3><p>The few big themes every reel should fit under.</p></div>';
    out+=d.pillars.length?'<div class="pillars">'+each(d.pillars,function(p,i){
      return '<div class="pillar"><span class="pn">'+(i<9?'0':'')+(i+1)+'</span><p class="pt">'+md(p[0])+'</p>'+(p[1]?'<p class="pd">'+md(p[1])+'</p>':'')+
        (p[2]?'<a class="pproof" href="'+esc(p[2])+'" target="_blank" rel="noopener">'+esc(p[3]||'Proof')+' <span aria-hidden="true">↗</span></a>':'')+'</div>'})+'</div>'
      :empty('No pillars saved yet','Claude names your pillars from your best reels during a refresh.','refresh my research');
    var cols='';
    if(d.reddit){
      cols+='<div class="tcol"><div class="sub-head"><h3>Reddit</h3><p>The top threads in your subreddits'+(d.reddit.date?', collected '+esc(d.reddit.date):'')+'.</p></div>'+each(d.reddit.groups,function(g){
        return '<div class="rgroup"><h4>'+esc(g.where)+' <span>'+g.items.length+' threads</span></h4>'+each(g.items,function(it,i){
          return '<article class="thread'+(i>=6?' is-more':'')+'"><span class="t-rank">#'+esc(it.rank)+'</span><div class="t-body">'+
            '<a class="t-title" href="'+esc(it.url)+'" target="_blank" rel="noopener">'+esc(it.title)+'</a>'+(it.text?'<p class="t-text">'+esc(it.text)+'</p>':'')+
            (it.coms.length?'<div class="t-coms"><p class="k">What people said</p>'+each(it.coms,function(c){return '<blockquote>'+esc(c)+'</blockquote>'})+'</div>':'')+
            '<p class="t-meta">Top of the '+esc(it.period)+(it.posted!=null?' \u00b7 '+esc(it.posted):'')+'</p></div></article>'})+
          (g.items.length>6?more('r:'+g.where,g.items.length):'')+'</div>'})+'</div>';
    }else cols+='<div class="tcol"><div class="sub-head"><h3>Reddit</h3></div>'+empty('No Reddit threads yet','Tell Claude the subreddits your audience reads and it pulls the top threads and comments.','add subreddits to my research')+'</div>';
    if(d.x){
      var ps=d.x.posts;
      cols+='<div class="tcol"><div class="sub-head"><h3>X</h3><p>Popular posts from the accounts and searches you follow'+(d.x.date?', collected '+esc(d.x.date):'')+'.</p></div><div class="xlist">'+each(ps,function(p,i){
        return '<article class="xpost'+(i>=8?' is-more':'')+'"><p class="x-top"><b>'+esc(p.where)+'</b><span>'+esc(p.likes)+' likes</span>'+(p.posted!=null?'<span>'+esc(p.posted)+'</span>':'')+'</p>'+
          '<p class="x-text">'+esc(p.text).replace(/\n/g,'<br>')+'</p>'+ext(p.url,'Open on X')+'</article>'})+'</div>'+(ps.length>8?more('x',ps.length):'')+'</div>';
    }else cols+='<div class="tcol"><div class="sub-head"><h3>X</h3></div>'+empty('No X posts yet','Give Claude a few X accounts or search terms and it pulls what is popular there.','add X searches to my research')+'</div>';
    return out+'<div class="tcols">'+cols+'</div>';
  }

  /* ---- top of the page ---- */
  function hero(d){
    var sub=[];
    if(d.own) sub.push('<b>@'+esc(d.own)+'</b>');
    if(d.niche) sub.push('<span>'+esc(d.niche)+'</span>');
    return '<p class="eyebrow"><span class="dot"></span>'+esc(d.eyebrow)+'</p><h1 class="name">'+esc(d.name)+'</h1><p class="subline">'+sub.join(' ')+'</p>'+
      '<div class="stats">'+each(d.tiles,function(t){
        return '<div class="stat'+(t.hl?' hl':'')+'"><p class="num">'+esc(t.num)+'</p><p class="lbl">'+esc(t.lbl)+'</p><p class="sub">'+
          (t.href?'<a href="'+esc(t.href)+'" target="_blank" rel="noopener">'+esc(t.sub)+'</a>':esc(t.sub))+'</p></div>'})+'</div>';
  }

  /* ---- render, keeping what the viewer had open ---- */
  var panels=[].slice.call(document.querySelectorAll('[data-panel]')), tabs=[].slice.call(document.querySelectorAll('[data-tab]'));
  function panel(id){return document.querySelector('[data-panel="'+id+'"]')}
  function expand(b){
    b.parentElement.querySelectorAll('.is-more').forEach(function(e){e.classList.remove('is-hidden')});
    b.remove();
  }
  function applyFilter(){
    document.querySelectorAll('.seg [data-filter]').forEach(function(x){x.classList.toggle('on',x.dataset.filter===st.filter)});
    var grid=$('my-grid'), n=0; if(!grid) return;
    grid.querySelectorAll('.card').forEach(function(c){var ok=st.filter==='all'||c.dataset.group===st.filter;c.hidden=!ok;if(ok)n++});
    var e=grid.parentElement.querySelector('.filter-empty'); if(e) e.hidden=n>0;
  }
  function filt(){
    var s=st.q.trim().toLowerCase(), n=0;
    document.querySelectorAll('.hookcard').forEach(function(c){
      var ok=(!s||c.dataset.text.indexOf(s)>-1)&&(!st.mech||c.dataset.mechs.split('|').indexOf(st.mech)>-1);
      c.hidden=!ok; if(ok) n++;
    });
    var e=document.querySelector('.bank-empty'); if(e) e.hidden=n>0;
  }
  function applyMech(){
    var chips=[].slice.call(document.querySelectorAll('.chip'));
    if(!chips.some(function(c){return c.dataset.mech===st.mech})) st.mech='';
    chips.forEach(function(c){c.classList.toggle('on',c.dataset.mech===st.mech)});
    filt();
  }
  function render(keep){
    var D=window.SS_DATA; if(!D) return;
    var y=window.scrollY, a=document.activeElement, qf=a&&a.id==='hook-q', sel=qf?[a.selectionStart,a.selectionEnd]:null;
    R=D.reels||{}; DT=[];
    document.title=D.hero.name+' \u00b7 Research';
    $('ss-brand').innerHTML=(SHELL.logo?'<img src="'+esc(SHELL.logo)+'" alt="'+esc(D.hero.name)+'">':'<span class="mono">'+esc(D.hero.initial)+'</span>')+'<span class="prod">Script Studio</span>';
    $('ss-hero').innerHTML=hero(D.hero);
    panel('reels').innerHTML=secMy(D.my);
    panel('hooks').innerHTML=secHooks(D.hooks);
    panel('competitors').innerHTML=secComp(D.comps);
    panel('topics').innerHTML=secTopics(D.topics);
    $('ss-foot').innerHTML='<span>Built by Script Studio on '+esc(D.built)+'.</span><span>Fresh numbers after every research refresh. Say "refresh my research".</span>';
    document.querySelectorAll('.is-more').forEach(function(e){e.classList.add('is-hidden')});
    document.querySelectorAll('[data-more]').forEach(function(b){if(st.more[b.dataset.more]) expand(b)});
    applyFilter();
    var q=$('hook-q');
    if(q){q.value=st.q; if(qf){q.focus(); try{q.setSelectionRange(sel[0],sel[1])}catch(e){}}}
    applyMech();
    if(keep) window.scrollTo({top:y,left:0,behavior:'instant'});
  }

  function show(id,push){
    if(!panels.some(function(p){return p.dataset.panel===id})) id=panels[0]&&panels[0].dataset.panel;
    panels.forEach(function(p){p.hidden=p.dataset.panel!==id});
    tabs.forEach(function(t){t.setAttribute('aria-selected',t.dataset.tab===id?'true':'false')});
    if(push&&history.replaceState) history.replaceState(null,'','#'+id);
  }
  tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.tab,true);var m=document.querySelector('main');if(window.scrollY>m.offsetTop)window.scrollTo({top:m.offsetTop-80})})});

  document.addEventListener('click',function(ev){
    var b=ev.target.closest('[data-more]');
    if(b){st.more[b.dataset.more]=1; expand(b); return}
    var f=ev.target.closest('.seg [data-filter]');
    if(f){st.filter=f.dataset.filter; applyFilter(); return}
    var c=ev.target.closest('.chip');
    if(c){st.mech=c.dataset.mech; applyMech(); return}
  });
  document.addEventListener('input',function(ev){if(ev.target.id==='hook-q'){st.q=ev.target.value; filt()}});

  var dlg=$('dlg'), body=$('dlg-body'), last=null;
  function open(id,from){
    var e=DT[parseInt(String(id).slice(1),10)-1]; if(!e||!R[e[0]]||!dlg) return;
    body.innerHTML=reelDetail(R[e[0]],e[1]); last=from;
    if(dlg.showModal){dlg.showModal()}else{dlg.setAttribute('open','')}
    var s=dlg.querySelector('.dlg-in'); if(s) s.scrollTop=0;
  }
  function close(){ if(dlg.close){dlg.close()}else{dlg.removeAttribute('open')} }
  if(dlg){
    dlg.addEventListener('click',function(e){if(e.target===dlg) close()});
    dlg.addEventListener('close',function(){if(last&&document.contains(last)) last.focus()});
    dlg.querySelector('.x-close').addEventListener('click',close);
  }
  document.addEventListener('click',function(e){
    if(e.target.closest('a')||e.target.closest('dialog')) return;
    var c=e.target.closest('[data-open]'); if(c) open(c.dataset.open,c);
  });
  document.addEventListener('keydown',function(e){
    if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('[data-open]')){e.preventDefault();open(e.target.dataset.open,e.target)}
  });

  /* ---- live refresh: reload data.js every 20 s (a script tag, so it works from file://) ---- */
  var note=$('ss-upd'), noteT=null;
  function updated(){
    if(!note) return;
    note.innerHTML='<i></i>Updated just now'; note.classList.add('on');
    clearTimeout(noteT); noteT=setTimeout(function(){note.classList.remove('on')},6000);
  }
  function poll(){
    var s=document.createElement('script');
    s.src='data.js?t='+Date.now();
    s.onload=function(){
      s.remove();
      var D=window.SS_DATA;
      if(D&&D.generated!==cur){var first=cur===null; cur=D.generated; render(true); if(!first) updated()}
    };
    s.onerror=function(){s.remove()};
    document.head.appendChild(s);
  }
  if(window.SS_DATA){cur=window.SS_DATA.generated; render(false)}
  function fromHash(){show(decodeURIComponent((location.hash||'').slice(1)),false)}
  window.addEventListener('hashchange',fromHash);
  window.addEventListener('popstate',fromHash);
  document.addEventListener('click',function(e){
    var a=e.target.closest&&e.target.closest('a[href^="#"]'); if(!a) return;
    var id=decodeURIComponent(a.getAttribute('href').slice(1));
    if(!panels.some(function(p){return p.dataset.panel===id})) return;
    e.preventDefault(); show(id,true);
    var m=document.querySelector('main'); if(m) window.scrollTo({top:Math.max(0,m.offsetTop-80)});
  });
  fromHash();
  setInterval(poll,20000);
})();
"""


# ---------- build ----------

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


EMDASH = re.compile('\\s*\u2014\\s*')


def no_dashes(o):
    """Never an em dash anywhere on the page."""
    if isinstance(o, str):
        return EMDASH.sub(', ', o)
    if isinstance(o, list):
        return [no_dashes(v) for v in o]
    if isinstance(o, dict):
        return {k: no_dashes(v) for k, v in o.items()}
    return o


def write_atomic(path, text):
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    os.replace(tmp, path)


SHELL_VERSION = 2   # bump when shell_page() changes; CSS and JS changes are picked up on their own
TABS = [('reels', 'My reels', 'My reels'), ('hooks', 'My hook library', 'Hooks'), ('competitors', 'Competitors', 'Competitors'), ('topics', 'Topics', 'Topics')]


def shell_page(br, logo):
    fonts = ''.join('<link rel="stylesheet" href="%s">' % esc(u) for u in br['links'])
    pre = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' if fonts else ''
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Research</title><meta name="color-scheme" content="%s">%s%s<style>%s%s</style></head><body>'
        '<header class="top"><div class="wrap top-in"><div class="brand" id="ss-brand"></div>'
        '<nav class="tabs" role="tablist" aria-label="Sections">%s</nav></div></header>'
        '<section class="hero wrap" id="ss-hero"></section>'
        '<main class="wrap">%s</main>'
        '<footer class="foot"><div class="wrap" id="ss-foot"></div></footer>'
        '<dialog id="dlg" aria-label="Reel details"><div class="dlg-in"><button class="x-close" aria-label="Close">×</button><div id="dlg-body"></div></div></dialog>'
        '<p class="upd" id="ss-upd" role="status" aria-live="polite"></p>'
        '<script src="data.js"></script><script>window.SS_SHELL=%s;%s</script></body></html>') % (
        'light' if br['light'] else 'dark', pre, fonts, css_vars(br), CSS,
        ''.join('<button role="tab" data-tab="%s" aria-selected="false"><span class="l">%s</span><span class="s">%s</span></button>' % t for t in TABS),
        ''.join('<section class="panel" data-panel="%s" aria-label="%s"></section>' % (t[0], t[1]) for t in TABS),
        json.dumps({'logo': logo or ''}), JS)
    return EMDASH.sub(', ', page)


def shell_sig(logo):
    """Changes when brand.json, the logo or the page template changes; then the shell is written again."""
    try:
        with open(os.path.join(ST, 'brand.json'), 'rb') as fh:
            raw = fh.read()
    except Exception:
        raw = b''
    h = hashlib.sha256()
    for part in (raw, (logo or '').encode(), str(SHELL_VERSION).encode(), CSS.encode(), JS.encode(), repr(TABS).encode()):
        h.update(part)
        h.update(b'\0')
    return h.hexdigest()[:20]


def build_shell(force):
    """Writes index.html only when it is missing, the brand changed, or force. True when it was written."""
    br = load_brand()
    os.makedirs(OUT, exist_ok=True)
    logo = copy_logo(br['logo'])
    sig = shell_sig(logo)
    path, mark = os.path.join(OUT, 'index.html'), os.path.join(OUT, '.shell')
    old = (read_json(mark, {}) or {}).get('sig') if os.path.isfile(mark) else None
    if not force and os.path.isfile(path) and old == sig:
        return br, False
    write_atomic(path, shell_page(br, logo))
    write_atomic(mark, json.dumps({'sig': sig, 'built': dt.datetime.now().astimezone().isoformat(timespec='seconds')}) + '\n')
    return br, True


def build_data(br):
    prof = read_json(os.path.join(ST, 'profile.json'), {}) or {}
    own = (prof.get('handle') or '').lower()
    libs = load_libraries()
    od = libs.get(own)
    comps = [c for c in (prof.get('competitors') or []) if c and c != own]
    comps += [h for h, d in libs.items() if h != own and h not in comps and len(d['reels']) >= 8]
    bank = parse_hook_bank()
    voice = read_text(os.path.join(ST, 'voice.md'))
    reddit, rdate = latest_radar('reddit')
    xs, xdate = latest_radar('x')

    # every picture the page shows: only the new ones are copied or downloaded
    jobs = []
    if od:
        jobs += [image_job(own, r) for r in od['reels']]
    for h in comps:
        d = libs.get(h)
        if d:
            jobs += [image_job(h, r) for r in d['reels'] if (r.get('x') or 0) >= 2 and (counts(r) or r.get('fresh'))]
    imgs = prepare_images([j for j in jobs if j])

    rv = Reels(imgs)
    my = data_my(own, od, rv)
    hooks = data_hooks(own, od, rv, bank, voice, banned_phrases(read_text(os.path.join(ST, 'about.md')), voice))
    cps = data_comps(comps, libs, rv)
    topics = data_topics(voice, reddit, rdate, xs, xdate)

    name = br['name'] or about_name() or prof.get('name') or ('@' + own if own else 'Your research')
    day = research_day(libs, [d for d in (rdate, xdate) if d])
    settled = sorted([r for r in (od or {}).get('reels', []) if counts(r) and not r.get('suspect')], key=lambda r: r['x'], reverse=True)
    best = settled[0] if settled else None
    n_comp = len([h for h in comps if h in libs])
    tiles = [
        {'num': fmt_n(od.get('median_views')), 'lbl': 'views on your usual reel', 'sub': 'The middle of your %d settled reels' % len(settled)} if od else
        {'num': '0', 'lbl': 'views on your usual reel', 'sub': 'Shows up after your first research run'},
        {'hl': 1, 'num': fmt_x(best['x']), 'lbl': 'your best reel vs your usual', 'href': best.get('url', '#'),
         'sub': '%s views, posted %s' % (fmt_n(best['views']), fmt_date(best.get('posted')))} if best else
        {'hl': 1, 'num': '0x', 'lbl': 'your best reel vs your usual', 'sub': 'Shows up after your first research run'},
        {'num': str(sum(len(d['reels']) for d in libs.values())), 'lbl': 'reels studied',
         'sub': 'Yours and %d competitor%s, %d transcribed' % (n_comp, '' if n_comp == 1 else 's',
                                                              sum(1 for d in libs.values() for r in d['reels'] if r.get('transcribed')))},
    ]
    data = no_dashes({
        'v': 1,
        'generated': dt.datetime.now().astimezone().isoformat(timespec='milliseconds'),
        'built': fmt_date(dt.date.today().isoformat(), True),
        'hero': {'name': name, 'initial': (name.lstrip('@') or 'S')[:1].upper(), 'own': own, 'niche': prof.get('niche') or '',
                 'eyebrow': ('Research updated %s · %s' % (fmt_date(day, True), ago(day))) if day else 'No research yet', 'tiles': tiles},
        'my': my, 'hooks': hooks, 'comps': cps, 'topics': topics, 'reels': rv.map,
    })
    write_atomic(os.path.join(OUT, 'data.js'),
                 'window.SS_DATA=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
    tidy_images([v['img'] for v in rv.map.values()])


def build(rebuild=False):
    br, built = build_shell(rebuild)
    build_data(br)
    return os.path.join(OUT, 'index.html'), built


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
    ap = argparse.ArgumentParser(prog='dashboard.py', description='Build or refresh the Script Studio research dashboard.')
    ap.add_argument('--open', action='store_true', help='open it in the default browser')
    ap.add_argument('--rebuild', action='store_true', help='write the page shell again too (after a brand change)')
    a = ap.parse_args()
    path, built = build(a.rebuild)
    if a.open:
        open_file(path)
    print('DASHBOARD %s' % path)
    print('BUILT shell+data' if built else 'UPDATED data')


if __name__ == '__main__':
    main()
