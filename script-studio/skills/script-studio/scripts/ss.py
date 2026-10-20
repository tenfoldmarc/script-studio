#!/usr/bin/env python3
"""Script Studio engine. Research in, ready-to-record scripts out (Claude writes; this gathers and ranks).

Run with the Creator Studio's own Python (start.sh / start.ps1 find it). Commands:
  check                                   STATUS lines (never shown to the buyer)
  key [--clipboard]                       save the buyer's Apify token (stdin, clipboard or hidden prompt)
  profile show | profile set --handle .. --competitors a,b --subreddits a,b --x-handles a,b
                 --x-search "a;b" --sites url,url --niche ".." --vocab "Brand,Product,KEYWORD" [--add] [--remove]
  scrape own|competitors|<handle,handle> [--limit 40] [--since "6 months"] [--max-usd 1.5]
  transcribe [--own-top 10] [--own-bottom 4] [--per-creator 4] [--min-x 2.5] [--model small.en]
  reddit [--subs a,b] [--period week|month|year] [--limit 12] [--comments 1]   (slow: Reddit rate-limits; run in the background)
  x [--handles a,b] [--search "a;b"] [--max 60]
  quick [--since "10 days"]               fresh research for an ideas session (new reels, new outliers, X, brief)
  brief [--days 120]                      writes research/brief.md (what Claude reads to find ideas)
  import <file | Apify dataset id>        reels collected another way (Apify connector, export)
  import-x <file | Apify dataset id>      X posts collected with the Apify connector
  library [--handle h] [--top 20]         ranked list of scraped reels
  where                                   prints the folders

Every file lives in the buyer's own Script Studio folder (outside the plugin, so updates never erase it).
The Apify token is never printed, never put in a URL and never passed as an argument.
"""
import argparse
import datetime as dt
import getpass
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True
APP = 'script-studio'
STUDIO_APP = 'video-studio'
VERSION = '1.0.0'
REEL_ACTOR = 'apify~instagram-reel-scraper'
X_ACTOR = 'apidojo~tweet-scraper'
REEL_PRICE = 0.0026          # Apify free-tier price per reel (the most a buyer pays per reel)
TWEET_PRICE = 0.0004
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ScriptStudio/1.0'
FRESH_DAYS = 3               # views on a post younger than this are still climbing: never part of a median


def utf8_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


# ---------- folders ----------

def os_name():
    if sys.platform == 'darwin':
        return 'macos'
    if sys.platform.startswith('win'):
        return 'windows'
    return 'linux'


def data_dir(app):
    home = os.path.expanduser('~')
    osn = os_name()
    if osn == 'macos':
        return os.path.join(home, 'Library', 'Application Support', app)
    if osn == 'windows':
        return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.join(home, 'AppData', 'Local'), app)
    xdg = os.environ.get('XDG_DATA_HOME') or ''
    return os.path.join(xdg if xdg.startswith('/') else os.path.join(home, '.local', 'share'), app)


ST = os.environ.get('SCRIPT_STUDIO_STATE') or data_dir(APP)
P = {
    'profile': os.path.join(ST, 'profile.json'),
    'key': os.path.join(ST, 'apify.env'),
    'library': os.path.join(ST, 'library'),
    'research': os.path.join(ST, 'research'),
    'about': os.path.join(ST, 'about.md'),
    'ideas': os.path.join(ST, 'ideas'),
    'scripts': os.path.join(ST, 'scripts'),
    'taste': os.path.join(ST, 'taste.md'),
    'hookbank': os.path.join(ST, 'hook-bank.md'),
    'voice': os.path.join(ST, 'voice.md'),
    'log': os.path.join(ST, 'research', 'transcribe.log'),
}


def apply_scripts_dir():
    p = read_json(P['profile'], {}) or {}
    if p.get('scripts_dir'):
        P['scripts'] = os.path.expanduser(p['scripts_dir'])


def ensure_dirs():
    apply_scripts_dir()
    for k in ('library', 'research', 'ideas', 'scripts'):
        os.makedirs(P[k], exist_ok=True)


def read_json(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return fallback


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def studio_platform():
    return read_json(os.path.join(data_dir(STUDIO_APP), '.platform.json'), {}) or {}


def ffmpeg():
    p = studio_platform().get('ffmpeg')
    if p and os.path.exists(p):
        return p
    return 'ffmpeg'


def today():
    return dt.date.today().isoformat()


def clean_handle(h):
    h = (h or '').strip()
    m = re.search(r'(?:instagram\.com|x\.com|twitter\.com|tiktok\.com)/@?([A-Za-z0-9._]+)', h)
    if m:
        h = m.group(1)
    return h.lstrip('@').strip('/').lower()


def split_list(v, sep=','):
    if not v:
        return []
    return [x.strip() for x in v.split(sep) if x.strip()]


# ---------- Apify ----------

def token():
    try:
        with open(P['key'], encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('APIFY_TOKEN='):
                    return line.split('=', 1)[1].strip()
    except OSError:
        pass
    return None


def apify(method, path, body=None, tok=None, timeout=60):
    tok = tok or token()
    if not tok:
        raise SystemExit('STATUS apify MISSING')
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request('https://api.apify.com/v2' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def apify_user(tok):
    try:
        d = apify('GET', '/users/me', tok=tok, timeout=20)['data']
        return d.get('username') or 'ok', (d.get('plan') or {}).get('id') or ''
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, 'invalid'
        return None, 'http %s' % e.code
    except Exception as e:
        return None, 'offline (%s)' % e.__class__.__name__


class NeedConnector(Exception):
    """No Apify key saved: the buyer has Apify connected inside Claude instead. The plan was printed; Claude runs
    the actor with its Apify tool and hands the dataset back with `import` / `import-x`."""


def run_actor(actor, inp, max_usd, label):
    """Start an actor, wait for it, return its dataset items. Prints progress lines (plain words).
    Without a saved key it prints the actor and its input for the Apify connector, then raises NeedConnector."""
    if not token():
        print('CONNECTOR %s %s' % (label, actor.replace('~', '/')))
        print('INPUT %s' % json.dumps(inp, ensure_ascii=False))
        raise NeedConnector(label)
    q = urllib.parse.urlencode({'maxTotalChargeUsd': '%.2f' % max_usd})
    run = apify('POST', '/acts/%s/runs?%s' % (actor, q), inp)['data']
    rid, ds = run['id'], run['defaultDatasetId']
    print('RUN %s started (%s)' % (label, rid), flush=True)
    t0 = time.time()
    status = run.get('status')
    while status in ('READY', 'RUNNING'):
        time.sleep(5)
        status = apify('GET', '/actor-runs/%s' % rid)['data'].get('status')
        if time.time() - t0 > 1800:
            raise SystemExit('FAILED %s took over 30 minutes' % label)
    if status != 'SUCCEEDED':
        print('WARN %s ended %s; keeping whatever it collected' % (label, status), flush=True)
    items, off = [], 0
    while True:
        chunk = apify('GET', '/datasets/%s/items?clean=true&offset=%d&limit=500' % (ds, off), timeout=120)
        if isinstance(chunk, dict):
            chunk = chunk.get('data', {}).get('items', [])
        items.extend(chunk)
        if len(chunk) < 500:
            break
        off += 500
    print('RUN %s done: %d items in %ds' % (label, len(items), time.time() - t0), flush=True)
    return items


# ---------- profile ----------

PROFILE_LISTS = ('competitors', 'subreddits', 'x_handles', 'x_search', 'sites')


def load_profile():
    p = read_json(P['profile'], {}) or {}
    for k in PROFILE_LISTS:
        p.setdefault(k, [])
    p.setdefault('vocab', [])
    return p


def cmd_profile(a):
    p = load_profile()
    if a.action == 'show':
        print(json.dumps(p, indent=1, ensure_ascii=False))
        return
    if a.handle:
        p['handle'] = clean_handle(a.handle)
    for k in ('niche', 'name', 'goal', 'offer', 'cta', 'scripts_dir', 'website', 'lang'):
        v = getattr(a, k, None)
        if v:
            p[k] = v.strip()
    seps = {'x_search': ';'}
    for k in PROFILE_LISTS + ('vocab',):
        v = getattr(a, k, None)
        if v is None:
            continue
        vals = split_list(v, seps.get(k, ','))
        if k in ('competitors', 'x_handles'):
            vals = [clean_handle(x) for x in vals]
        if k == 'subreddits':
            vals = [re.sub(r'^(https?://)?(www\.)?reddit\.com/', '', x).strip('/').replace('r/', '', 1) for x in vals]
        if a.remove:
            p[k] = [x for x in p[k] if x not in vals]
        elif a.add:
            p[k] = p[k] + [x for x in vals if x not in p[k]]
        else:
            p[k] = vals
    p.setdefault('created', today())
    p['updated'] = today()
    write_json(P['profile'], p)
    print('PROFILE saved: @%s, %d competitors, %d subreddits, %d X accounts, %d X searches, %d sites' % (
        p.get('handle', '?'), len(p['competitors']), len(p['subreddits']), len(p['x_handles']),
        len(p['x_search']), len(p['sites'])))


# ---------- key ----------

def read_clipboard():
    osn = os_name()
    cmds = {'macos': ['pbpaste'], 'windows': ['powershell', '-NoProfile', '-Command', 'Get-Clipboard'],
            'linux': ['xclip', '-selection', 'clipboard', '-o']}
    try:
        return subprocess.run(cmds[osn], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ''


def cmd_key(a):
    if a.clipboard:
        raw = read_clipboard()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raw = getpass.getpass('Paste your Apify API token (hidden), then Enter: ')
    m = re.search(r'apify_api_[A-Za-z0-9]{20,}', raw or '')
    tok = m.group(0) if m else (raw or '').strip()
    if not tok or len(tok) < 20 or ' ' in tok:
        print('KEY NOT_FOUND (no Apify token on the clipboard / in the input)')
        return
    user, plan = apify_user(tok)
    if not user:
        print('KEY INVALID (%s)' % plan)
        return
    os.makedirs(ST, exist_ok=True)
    with open(P['key'], 'w', encoding='utf-8') as fh:
        fh.write('APIFY_TOKEN=%s\n' % tok)
    try:
        os.chmod(P['key'], 0o600)
    except OSError:
        pass
    print('KEY saved (Apify account %s, plan %s)' % (user, plan or 'free'))


# ---------- reels ----------

def lib_file(handle):
    return os.path.join(P['library'], handle, 'reels.json')


def reel_dir(handle, code):
    return os.path.join(P['library'], handle, code)


def parse_ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


def norm_reel(it):
    views = it.get('videoPlayCount') or it.get('videoViewCount') or 0
    return {
        'code': it.get('shortCode'),
        'url': it.get('url') or ('https://www.instagram.com/reel/%s/' % it.get('shortCode')),
        'handle': (it.get('ownerUsername') or '').lower(),
        'posted': it.get('timestamp'),
        'views': int(views or 0),
        'likes': int(it.get('likesCount') or 0) if (it.get('likesCount') or 0) >= 0 else 0,
        'comments': int(it.get('commentsCount') or 0),
        'duration': round(float(it.get('videoDuration') or 0), 1),
        'caption': (it.get('caption') or '').strip(),
        'pinned': bool(it.get('isPinned')),
        'collab': bool(it.get('paidPartnership')) or bool(it.get('coauthorProducers')),   # paid or shared post: weigh lightly
        'audio': (it.get('musicInfo') or {}).get('song_name') or '',
        'original_audio': (it.get('musicInfo') or {}).get('uses_original_audio'),
        'audio_url': it.get('audioUrl'),
        'video_url': it.get('videoUrl'),
        'cover_url': it.get('displayUrl'),
        'top_comments': [c.get('text', '') for c in (it.get('latestComments') or [])[:8] if c.get('text')],
        'scraped': today(),
    }


def mark_repeats(reels):
    """The same video posted twice (a re-upload or a repost of a winner): same length to a fraction of a second,
    plus a similar caption or the same audio. The copy with fewer views is marked `repeat`: it is never a winner,
    a flop or part of the median."""
    import difflib
    for r in reels:
        r['repeat'] = False
    by_len = sorted([r for r in reels if r.get('duration', 0) > 5], key=lambda r: r['duration'])
    for i, a in enumerate(by_len):
        for b in by_len[i + 1:]:
            if b['duration'] - a['duration'] > 0.3:
                break
            same_cap = difflib.SequenceMatcher(None, first_line(a['caption'], 120).lower(), first_line(b['caption'], 120).lower()).ratio() > 0.55
            same_audio = a.get('audio') and a.get('audio') == b.get('audio') and not a.get('original_audio')
            if abs(b['duration'] - a['duration']) <= 0.12 or same_cap or same_audio:
                lo = a if a['views'] < b['views'] else b
                lo['repeat'] = True


def counts(r):
    """In medians, winners and flops: settled, not pinned, not a repeat."""
    return not r.get('fresh') and not r.get('pinned') and not r.get('repeat') and r['views'] > 0


def score(reels):
    """Multiplier = views / that creator's median views (settled posts only: older than FRESH_DAYS, no repeats)."""
    now = dt.datetime.now(dt.timezone.utc)
    mark_repeats(reels)
    settled = [r['views'] for r in reels if r['views'] > 0 and not r['pinned'] and not r.get('repeat')
               and (parse_ts(r['posted'] or '') or now) < now - dt.timedelta(days=FRESH_DAYS)]
    med = statistics.median(settled) if len(settled) >= 5 else (statistics.median([r['views'] for r in reels if r['views']] or [0]) or 0)
    for r in reels:
        ts = parse_ts(r['posted'] or '')
        r['age_days'] = (now - ts).days if ts else None
        r['fresh'] = r['age_days'] is not None and r['age_days'] < FRESH_DAYS
        r['x'] = round(r['views'] / med, 2) if med else 0
        # under a tenth of the usual: almost always a re-upload, a trial reel or a post Instagram held back,
        # not a real verdict on the content. Kept out of the flops; the brief lists it to check by its frames.
        r['suspect'] = bool(med) and not r['fresh'] and not r.get('repeat') and r['x'] < 0.1
    return med


def save_reels(handle, new):
    old = {r['code']: r for r in (read_json(lib_file(handle), {}) or {}).get('reels', [])}
    for r in new:
        keep = old.get(r['code'], {})
        for k in ('transcribed', 'frames', 'transcript_file'):
            if k in keep:
                r[k] = keep[k]
        old[r['code']] = r
    reels = sorted(old.values(), key=lambda r: r.get('posted') or '', reverse=True)
    med = score(reels)
    write_json(lib_file(handle), {'handle': handle, 'median_views': med, 'updated': today(), 'reels': reels})
    return med, reels


def fmt_n(n):
    n = n or 0
    if n >= 1_000_000:
        return '%.1fM' % (n / 1e6)
    if n >= 1000:
        return '%.1fK' % (n / 1e3)
    return str(int(n))


def cmd_scrape(a):
    ensure_dirs()
    p = load_profile()
    if a.who == 'own':
        handles = [p.get('handle')] if p.get('handle') else []
    elif a.who == 'competitors':
        handles = p['competitors']
    else:
        handles = [h.split('?')[0] if re.search(r'instagram\.com/(reel|reels|p)/', h) else clean_handle(h) for h in split_list(a.who)]
    handles = [h for h in handles if h]
    if not handles:
        raise SystemExit('FAILED no handles to scrape (profile has none)')
    est = len(handles) * a.limit * REEL_PRICE + 0.01
    cap = max(min(a.max_usd, est * 3), est * 1.3)
    print('PLAN %d account(s) x up to %d reels, about $%.2f of Apify credit (hard cap $%.2f)' % (len(handles), a.limit, est, cap), flush=True)
    # trial reels go to non-followers only and look like flops: never part of the research
    inp = {'username': handles, 'resultsLimit': a.limit, 'skipPinnedPosts': True, 'skipTrialReels': True}
    if a.since:
        inp['onlyPostsNewerThan'] = a.since
    try:
        items = run_actor(REEL_ACTOR, inp, cap, 'reels')
    except NeedConnector:
        print('NEXT run that actor with the Apify tool (wait until it finishes), then: import <datasetId>')
        return
    ingest(items, a.who if a.who in ('own', 'competitors') else 'custom', handles)


def ingest(items, label, expected=()):
    write_json(os.path.join(P['research'], 'raw', '%s-reels-%s.json' % (today(), label)), items)
    by = {}
    for it in items:
        if not it.get('shortCode') or it.get('error'):
            continue
        r = norm_reel(it)
        if not r['handle']:
            continue
        by.setdefault(r['handle'], []).append(r)
    for h, rs in by.items():
        # Pinned reels are not always flagged: an old reel sitting in the first 3 places of the grid, posted weeks
        # before the reels around it, is a pinned one. Kept, but never a winner, a flop or part of the median.
        later = sorted([parse_ts(r['posted'] or '') for r in rs[3:9] if parse_ts(r['posted'] or '')])
        if later:
            for r in rs[:3]:
                ts = parse_ts(r['posted'] or '')
                if ts and ts < later[0] - dt.timedelta(days=21):
                    r['pinned'] = True
        med, reels = save_reels(h, rs)
        top = sorted([r for r in reels if counts(r)], key=lambda r: r['x'], reverse=True)[:5]
        print('ACCOUNT @%s: %d reels, median %s views. Best: %s' % (
            h, len(reels), fmt_n(med), ', '.join('%sx (%s)' % (r['x'], fmt_n(r['views'])) for r in top)))
    for h in expected:
        if h not in by and '/' not in h:
            print('MISSING @%s: no reels came back (private, wrong handle, or no reels)' % h)


def load_items(src):
    if os.path.exists(src):
        items = read_json(src, [])
    else:
        ds = re.sub(r'.*/datasets/', '', src).split('/')[0].split('?')[0]
        hdr = {'User-Agent': UA}
        if token():
            hdr['Authorization'] = 'Bearer ' + token()
        with urllib.request.urlopen(urllib.request.Request('https://api.apify.com/v2/datasets/%s/items?clean=true' % ds, headers=hdr), timeout=120) as r:
            items = json.load(r)
    if isinstance(items, dict):
        items = items.get('items') or items.get('data', {}).get('items', [])
    return items


def cmd_import_x(a):
    items = load_items(a.source)
    print('IMPORT %d X posts' % len(items))
    x_ingest(items)


def cmd_import(a):
    """Reels collected some other way (the Apify connector in Claude, a JSON export): a file or a dataset id."""
    ensure_dirs()
    src = a.source
    if os.path.exists(src):
        items = read_json(src, [])
    else:
        ds = re.sub(r'.*/datasets/', '', src).split('/')[0].split('?')[0]
        url = 'https://api.apify.com/v2/datasets/%s/items?clean=true' % ds
        hdr = {'User-Agent': UA}
        if token():
            hdr['Authorization'] = 'Bearer ' + token()
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=120) as r:
            items = json.load(r)
    if isinstance(items, dict):
        items = items.get('items') or items.get('data', {}).get('items', [])
    print('IMPORT %d items' % len(items))
    ingest(items, 'import')


def cmd_quick(a):
    """Fresh research for an ideas session: the newest reels of the buyer and every competitor in ONE Apify run
    (only posts from the last few days, so it is cheap), transcripts of any new outliers, and X if set up.
    Reddit is slow, so it is started separately (in the background) and websites are read by Claude."""
    ensure_dirs()
    p = load_profile()
    handles = [h for h in ([p.get('handle')] + p['competitors']) if h]
    if not handles:
        raise SystemExit('FAILED no handles in the profile')
    est = len(handles) * a.limit * REEL_PRICE + 0.01
    print('PLAN newest reels of %d account(s) from the last %s, about $%.2f of Apify credit at most' % (len(handles), a.since, est), flush=True)
    inp = {'username': handles, 'resultsLimit': a.limit, 'onlyPostsNewerThan': a.since, 'skipTrialReels': True, 'skipPinnedPosts': True}
    if not token():   # Apify connected inside Claude: print both plans, Claude runs them and imports
        print('CONNECTOR reels %s' % REEL_ACTOR.replace('~', '/'))
        print('INPUT %s' % json.dumps(inp, ensure_ascii=False))
        if p['x_handles'] or p['x_search']:
            print('CONNECTOR x %s' % X_ACTOR.replace('~', '/'))
            print('INPUT %s' % json.dumps(x_input(p, argparse.Namespace(handles=None, search=None, max=60, days=7)), ensure_ascii=False))
        print('NEXT run each actor with the Apify tool, then: import <reels datasetId>, import-x <x datasetId>, transcribe, brief')
        return
    ingest(run_actor(REEL_ACTOR, inp, max(0.3, est * 1.3), 'reels'), 'quick')
    transcribe_all(argparse.Namespace(own_top=a.own_top, own_bottom=0, per_creator=2, min_x=a.min_x, model='small.en', codes=None))
    if p['x_handles'] or p['x_search']:
        try:
            cmd_x(argparse.Namespace(handles=None, search=None, max=60, days=7))
        except SystemExit as e:
            print('SKIP x (%s)' % e)
        except Exception as e:
            print('SKIP x (%s)' % e.__class__.__name__)
    cmd_brief(argparse.Namespace(days=120))


def cmd_library(a):
    hs = [clean_handle(a.handle)] if a.handle else sorted(os.listdir(P['library'])) if os.path.isdir(P['library']) else []
    for h in hs:
        d = read_json(lib_file(h))
        if not d:
            continue
        print('@%s median %s (updated %s)' % (h, fmt_n(d['median_views']), d['updated']))
        for r in sorted(d['reels'], key=lambda r: r.get('x', 0), reverse=True)[:a.top]:
            tags = ''.join(t for t, on in ((' [T]', r.get('transcribed')), (' [fresh]', r.get('fresh')), (' [repeat]', r.get('repeat')),
                                            (' [collab or paid]', r.get('collab')), (' [pinned]', r.get('pinned')), (' [suspect]', r.get('suspect'))) if on)
            print('  %5.1fx %7s  %s  %s%s  %s' % (r.get('x', 0), fmt_n(r['views']), (r['posted'] or '')[:10], r['code'],
                                              tags, first_line(r['caption'], 70)))


def first_line(s, n=90):
    s = (s or '').strip().split('\n')[0]
    return s if len(s) <= n else s[:n - 1] + '…'


# ---------- transcription ----------

def download(url, dest, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest + '.part', 'wb') as fh:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            fh.write(b)
    os.replace(dest + '.part', dest)


def pick_for_transcripts(a):
    p = load_profile()
    own = p.get('handle')
    picks = []
    want = set(split_list(getattr(a, 'codes', None)))
    if want:   # specific reels ("make my version of this reel"): just those
        for h in (sorted(os.listdir(P['library'])) if os.path.isdir(P['library']) else []):
            for r in (read_json(lib_file(h)) or {}).get('reels', []):
                if r['code'] in want or any(c in r['url'] for c in want):
                    picks.append((h, r))
        return picks
    for h in (sorted(os.listdir(P['library'])) if os.path.isdir(P['library']) else []):
        d = read_json(lib_file(h))
        if not d:
            continue
        settled = [r for r in d['reels'] if counts(r) and r.get('original_audio') is not False]
        ranked = sorted(settled, key=lambda r: r['x'], reverse=True)
        if h == own:
            chosen = ranked[:a.own_top] + [r for r in ranked[::-1][:a.own_bottom] if r not in ranked[:a.own_top]]
            # a few middle-of-the-road ones too: voice is learned from typical posts, not only hits
            mid = [r for r in ranked if 0.7 <= r['x'] <= 1.2][:5] if len(ranked) > 6 else []   # typical reels: how they really talk
            chosen += [r for r in mid if r not in chosen]
        else:
            chosen = [r for r in ranked if r['x'] >= a.min_x][:a.per_creator]
            if not chosen:   # no clear outlier: their single best still teaches something
                chosen = ranked[:1]
        picks += [(h, r) for r in chosen]
    return picks


def transcribe_all(a):
    picks = pick_for_transcripts(a)
    todo = [(h, r) for h, r in picks if not r.get('transcribed')]
    print('TRANSCRIBE %d reels picked, %d new' % (len(picks), len(todo)), flush=True)
    if not todo:
        return
    from faster_whisper import WhisperModel   # the Studio's Python has it
    model = WhisperModel(a.model, device='cpu', compute_type='int8')
    # names Whisper tends to mishear (the buyer's brand, product names, CTA keyword): passed as a hint
    prof = load_profile()
    hint = ', '.join([w for w in prof.get('vocab', []) if w] + ([prof['handle']] if prof.get('handle') else []))[:400] or None
    ff = ffmpeg()
    expired = []
    for i, (h, r) in enumerate(todo, 1):
        d = reel_dir(h, r['code'])
        os.makedirs(d, exist_ok=True)
        src = os.path.join(d, 'audio.mp4')
        try:
            if not os.path.exists(src):
                url = r.get('audio_url') or r.get('video_url')
                if not url:
                    raise RuntimeError('no media address')
                download(url, src)
            wav = os.path.join(d, 'audio.wav')
            subprocess.run([ff, '-loglevel', 'error', '-y', '-i', src, '-vn', '-ac', '1', '-ar', '16000', wav], check=True)
            segs, info = model.transcribe(wav, vad_filter=True, beam_size=1, initial_prompt=hint)
            lines = [{'start': round(s.start, 2), 'end': round(s.end, 2), 'text': s.text.strip()} for s in segs]
            text = ' '.join(x['text'] for x in lines).strip()
            write_json(os.path.join(d, 'transcript.json'), {'code': r['code'], 'lang': getattr(info, 'language', ''), 'segments': lines})
            with open(os.path.join(d, 'transcript.txt'), 'w', encoding='utf-8') as fh:
                fh.write(text + '\n')
            os.remove(wav)
            frames = grab_frames(ff, r, d)
            mark(h, r['code'], transcribed=today(), frames=frames, words=len(text.split()))
            print('DONE %d/%d @%s %s (%d words)' % (i, len(todo), h, r['code'], len(text.split())), flush=True)
        except urllib.error.HTTPError as e:
            if e.code in (403, 410):
                expired.append((h, r))
            print('SKIP %d/%d @%s %s (%s)' % (i, len(todo), h, r['code'], 'link expired' if e.code in (403, 410) else e), flush=True)
        except Exception as e:
            print('SKIP %d/%d @%s %s (%s)' % (i, len(todo), h, r['code'], e), flush=True)
    if expired:
        print('EXPIRED %d media links: run `scrape` again for those accounts, then transcribe again' % len(expired))


def grab_frames(ff, r, d):
    """Frame 1 (what the hook looks like, incl. on-screen text) and ~2 s in. Read straight from the video address."""
    out = []
    url = r.get('video_url')
    if not url:
        return out
    for t, name in ((0.4, 'frame-0.jpg'), (2.0, 'frame-2.jpg')):
        dest = os.path.join(d, name)
        try:
            subprocess.run([ff, '-loglevel', 'error', '-y', '-user_agent', UA, '-ss', str(t), '-i', url, '-frames:v', '1',
                            '-vf', 'scale=540:-2', '-q:v', '4', dest], check=True, timeout=60)
            out.append(name)
        except Exception:
            pass
    return out


def mark(h, code, **kv):
    d = read_json(lib_file(h))
    for r in d['reels']:
        if r['code'] == code:
            r.update(kv)
    write_json(lib_file(h), d)


def cmd_transcribe(a):
    ensure_dirs()
    transcribe_all(a)


# ---------- topic radar ----------

def rss_get(url, tries=3):
    """Reddit blocks its JSON for scripts but serves RSS; it rate-limits hard, so wait and retry on 429."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'ScriptStudio/%s (research for a creator)' % VERSION})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(15 * (i + 1))
                continue
            raise


def strip_html(h):
    import html as _h
    h = re.sub(r'<!-- SC_OFF -->|<!-- SC_ON -->', '', _h.unescape(h or ''))
    h = re.sub(r'submitted by.*$', '', h, flags=re.S)
    h = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', _h.unescape(h)).strip()


def atom_entries(xml):
    import xml.etree.ElementTree as ET
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    root = ET.fromstring(xml)
    out = []
    for e in root.findall('a:entry', ns):
        link = e.find('a:link', ns)
        out.append({'title': (e.findtext('a:title', '', ns) or '').strip(),
                    'url': link.get('href') if link is not None else '',
                    'text': strip_html(e.findtext('a:content', '', ns))[:700],
                    'author': (e.findtext('a:author/a:name', '', ns) or ''),
                    'posted': (e.findtext('a:published', '', ns) or e.findtext('a:updated', '', ns) or '')[:10]})
    return out


BOT_HINTS = ('generated automatically', 'tl;dr of the discussion', 'i am a bot', 'automoderator', 'featured it on our discord', 'welcome to /r/', 'welcome to r/',
             'your post has been removed', 'please contact the moderators', 'this is an automated')


def is_bot(c):
    t = (c.get('text', '') + ' ' + c.get('author', '')).lower()
    return any(h in t for h in BOT_HINTS)


def cmd_reddit(a):
    ensure_dirs()
    subs = split_list(a.subs) or load_profile()['subreddits']
    if not subs:
        raise SystemExit('FAILED no subreddits in the profile')
    out = []
    for s in subs:
        try:
            ents = atom_entries(rss_get('https://www.reddit.com/r/%s/top.rss?t=%s&limit=%d' % (urllib.parse.quote(s), a.period, a.limit)))
        except Exception as e:
            print('MISSING r/%s (%s)' % (s, e), flush=True)
            continue
        for rank, x in enumerate(ents, 1):
            x.update({'source': 'reddit', 'where': 'r/' + s, 'rank': rank, 'period': a.period})
        # the audience's own words: the top comments of the 2 hottest threads
        for x in ents[:a.comments]:
            time.sleep(3)
            try:
                cs = atom_entries(rss_get(x['url'].rstrip('/') + '/.rss?sort=top&limit=10'))[1:]
                x['top_comments'] = [c['text'][:300] for c in cs if c['text'] and not is_bot(c)][:6]
            except Exception:
                pass
        out += ents
        print('REDDIT r/%s: %d threads (top of the %s)' % (s, len(ents), a.period), flush=True)
        time.sleep(7)
    write_json(os.path.join(P['research'], 'radar', 'reddit-%s-%s.json' % (today(), a.period)), out)
    for it in sorted(out, key=lambda x: x['rank'])[:a.limit * 2]:
        print('  #%-2d %s  %s' % (it['rank'], it['where'], first_line(it['title'], 100)))


def cmd_x(a):
    ensure_dirs()
    p = load_profile()
    handles = [clean_handle(h) for h in split_list(a.handles)] or p['x_handles']
    searches = split_list(a.search, ';') or p['x_search']
    if not handles and not searches:
        raise SystemExit('FAILED no X accounts or searches in the profile')
    since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    terms = ['from:%s since:%s -filter:replies' % (h, since) for h in handles] + ['%s since:%s min_faves:50 -filter:replies' % (s, since) for s in searches]
    est = a.max * TWEET_PRICE + 0.01
    print('PLAN %d X searches, up to %d posts, about $%.2f of Apify credit at most' % (len(terms), a.max, est), flush=True)
    try:
        items = run_actor(X_ACTOR, x_input(p, a), max(0.25, est * 1.5), 'x')
    except NeedConnector:
        print('NEXT run that actor with the Apify tool, then: import-x <datasetId>')
        return
    x_ingest(items)


def x_terms(p, a):
    handles = [clean_handle(h) for h in split_list(getattr(a, 'handles', None))] or p['x_handles']
    searches = split_list(getattr(a, 'search', None), ';') or p['x_search']
    since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    return ['from:%s since:%s -filter:replies' % (h, since) for h in handles] + ['%s since:%s min_faves:50 -filter:replies' % (s, since) for s in searches]


def x_input(p, a):
    return {'searchTerms': x_terms(p, a), 'maxItems': a.max, 'sort': 'Top', 'includeSearchTerms': True, 'tweetLanguage': p.get('lang') or 'en'}


def x_ingest(items):
    ensure_dirs()
    out = []
    for t in items:
        if t.get('noResults') or not t.get('text'):
            continue
        out.append({'source': 'x', 'where': '@' + ((t.get('author') or {}).get('userName') or '?'), 'text': t.get('text', '')[:600],
                    'likes': t.get('likeCount', 0), 'reposts': t.get('retweetCount', 0), 'replies': t.get('replyCount', 0),
                    'views': t.get('viewCount', 0), 'url': t.get('url') or t.get('twitterUrl'), 'posted': t.get('createdAt', '')})
    write_json(os.path.join(P['research'], 'radar', 'x-%s-%d.json' % (today(), len(out))), out)
    print('X: %d posts kept' % len(out))
    for it in sorted(out, key=lambda x: x.get('likes') or 0, reverse=True)[:15]:
        print('  %6s likes  %s  %s' % (it['likes'], it['where'], first_line(it['text'].replace('\n', ' '), 90)))


# ---------- the brief ----------

def transcript(h, code):
    try:
        with open(os.path.join(reel_dir(h, code), 'transcript.txt'), encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError:
        return ''


def hook_line(h, code, secs=4.0):
    d = read_json(os.path.join(reel_dir(h, code), 'transcript.json'))
    if not d:
        return ''
    return ' '.join(s['text'] for s in d['segments'] if s['start'] < secs).strip()


def latest_radar(kind):
    d = os.path.join(P['research'], 'radar')
    fs = sorted((f for f in (os.listdir(d) if os.path.isdir(d) else []) if f.startswith(kind + '-')),
                key=lambda f: os.path.getmtime(os.path.join(d, f)))
    return (read_json(os.path.join(d, fs[-1]), []) or [], fs[-1][len(kind) + 1:-5]) if fs else ([], None)


def reel_block(h, r, full=True):
    frames = ', '.join(os.path.join(reel_dir(h, r['code']), f) for f in r.get('frames', []))
    t = transcript(h, r['code'])
    out = ['### @%s · %sx · %s views · %s · %ss%s' % (h, r['x'], fmt_n(r['views']), (r['posted'] or '')[:10], r['duration'],
                                                   ' · [collab or paid: weigh lightly]' if r.get('collab') else ''),
           r['url'],
           '- Caption: %s' % first_line(r['caption'], 220)]
    if t:
        out.append('- Spoken hook (first 4 s): "%s"' % hook_line(h, r['code']))
        if full:
            out.append('- Full transcript: %s' % t)
    if frames:
        out.append('- Frames (look for on-screen hook text): %s' % frames)
    if r.get('top_comments'):
        out.append('- Comments: ' + ' | '.join(first_line(c, 120) for c in r['top_comments'][:5]))
    return '\n'.join(out)


def cmd_brief(a):
    ensure_dirs()
    p = load_profile()
    own = p.get('handle')
    now = dt.datetime.now(dt.timezone.utc)
    L = ['# Research brief (%s)' % today(), '',
         'Read this before writing ideas. Outlier multiplier = views / that creator\'s own median.', '']
    od = read_json(lib_file(own)) if own else None
    n_win = 0
    if od:
        rs = [r for r in od['reels'] if counts(r)]
        rk = sorted(rs, key=lambda r: r['x'], reverse=True)
        wins = [r for r in rk if r['x'] >= 1.2][:8]
        flops = [r for r in rk[::-1] if r['x'] < 0.7 and r not in wins and not r.get('suspect')][:4]
        odd = [r for r in rk if r.get('suspect')]
        n_win = len(wins)
        skipped = [r for r in od['reels'] if r.get('fresh') or r.get('repeat')]
        L += ['## 1. Your account @%s (median %s views over %d settled reels)' % (own, fmt_n(od['median_views']), len(rs)), '']
        if skipped:
            L += ['Left out: %d posted in the last %d days (views still climbing), %d repeats of another reel.' % (
                sum(1 for r in skipped if r.get('fresh')), FRESH_DAYS, sum(1 for r in skipped if r.get('repeat'))), '']
        L += ['### Your winners (1.2x or more; study what they share: topic, hook, format, length)', '']
        L += [reel_block(own, r) + '\n' for r in wins] or ['- None above 1.2x yet. Your reels perform about the same: use competitor outliers as the main signal.\n']
        L += ['### Your weakest (under 0.7x; what to stop doing)', '']
        L += [reel_block(own, r) + '\n' for r in flops] or ['- None under 0.7x.\n']
        if odd:
            L += ['### Suspiciously low (under 0.1x: check the frames, likely a re-upload or a held-back post, not a flop)', '']
            L += ['- %s %sx %s views: %s' % (r['url'], r['x'], fmt_n(r['views']), first_line(r['caption'], 100)) for r in odd] + ['']
        lens = [r['duration'] for r in wins if r['duration']]
        if lens:
            L += ['Length of your winners: median %ss (all settled reels: %ss)' % (statistics.median(lens), statistics.median([r['duration'] for r in rs if r['duration']] or [0])), '']
    L += ['## 2. Competitor outliers (ranked by multiplier, last %d days)' % a.days, '']
    comp = []
    for h in p['competitors']:
        d = read_json(lib_file(h))
        if not d:
            L.append('- @%s: not scraped yet' % h)
            continue
        for r in d['reels']:
            ts = parse_ts(r['posted'] or '')
            if not counts(r) or (ts and ts < now - dt.timedelta(days=a.days)):
                continue
            comp.append((h, r))
    comp.sort(key=lambda hr: hr[1]['x'], reverse=True)
    shown = 0
    for h, r in comp:
        if r['x'] < 1.5 and shown >= 6:
            break
        if r.get('transcribed'):
            L.append(reel_block(h, r) + '\n')
            shown += 1
    untouched = [(h, r) for h, r in comp if not r.get('transcribed') and r['x'] >= 2][:15]
    if untouched:
        L += ['### More outliers (caption only, not transcribed yet)', '']
        L += ['- @%s %sx %s views: %s (%s)' % (h, r['x'], fmt_n(r['views']), first_line(r['caption'], 140), r['url']) for h, r in untouched]
        L.append('')
    rd, rdate = latest_radar('reddit')
    xd, xdate = latest_radar('x')
    if rd or xd:
        L += ['## 3. Topic radar (what the audience is talking about now)', '']
    if rd:
        L.append('### Reddit (%s)' % rdate)
        for it in sorted(rd, key=lambda x: x.get('rank', 99))[:30]:
            L.append('- [%s, #%s this %s] %s %s' % (it['where'], it.get('rank'), it.get('period', 'month'), it['title'], it['url']))
            if it.get('text'):
                L.append('  - post: %s' % first_line(it['text'], 240))
            for c in it.get('top_comments', [])[:3]:
                L.append('  - comment: %s' % first_line(c.replace('\n', ' '), 200))
        L.append('')
    if xd:
        L.append('### X (%s)' % xdate)
        for it in sorted(xd, key=lambda x: x.get('likes') or 0, reverse=True)[:25]:
            L.append('- [%s likes, %s] %s %s' % (it['likes'], it['where'], first_line(it['text'].replace('\n', ' '), 240), it['url']))
        L.append('')
    if p['sites']:
        L += ['### Sites to check yourself (fetch each, newest items only)', ''] + ['- ' + s for s in p['sites']] + ['']
    path = os.path.join(P['research'], 'brief.md')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L))
    print('BRIEF %s (%d words; own winners %d, competitor outliers %d, reddit %d, x %d)' % (
        path, sum(len(x.split()) for x in L), n_win, shown, len(rd), len(xd)))


# ---------- check ----------

def cmd_check(a):
    ensure_dirs()
    plat = studio_platform()
    py_ok = bool(plat.get('python')) and os.path.exists(plat.get('python', ''))
    print('STATUS studio %s' % ('OK' if py_ok else 'MISSING'))
    tok = token()
    if not tok:
        print('STATUS apify MISSING')
    else:
        user, why = apify_user(tok)
        print('STATUS apify %s' % ('OK' if user else ('INVALID' if why == 'invalid' else 'UNCHECKED ' + why)))
    p = read_json(P['profile'])
    print('STATUS profile %s' % ('OK @' + p.get('handle', '?') if p and p.get('handle') else 'MISSING'))
    print('STATUS voice %s' % ('OK' if os.path.exists(P['voice']) else 'MISSING'))
    print('STATUS about %s' % ('OK' if os.path.exists(P['about']) else 'MISSING'))
    libs = sorted(os.listdir(P['library'])) if os.path.isdir(P['library']) else []
    n_t = 0
    newest = ''
    for h in libs:
        d = read_json(lib_file(h)) or {}
        n_t += sum(1 for r in d.get('reels', []) if r.get('transcribed'))
        newest = max(newest, d.get('updated', ''))
    age = (dt.date.today() - dt.date.fromisoformat(newest)).days if newest else None
    print('STATUS research %s' % ('MISSING' if not libs else '%d accounts, %d transcripts, %d days old' % (len(libs), n_t, age)))
    if age is not None and age >= 7:
        print('STATUS research STALE')
    prof = load_profile()
    missing = [h for h in prof['competitors'] if not os.path.exists(lib_file(h))]
    if libs and missing:
        print('STATUS competitors MISSING %s' % ','.join(missing))
    if prof['subreddits'] or prof['x_handles'] or prof['x_search']:
        rdir = os.path.join(P['research'], 'radar')
        fs = [os.path.join(rdir, f) for f in (os.listdir(rdir) if os.path.isdir(rdir) else []) if f.endswith('.json')]
        if fs:
            print('STATUS radar %d days old' % int((time.time() - max(os.path.getmtime(f) for f in fs)) // 86400))
        else:
            print('STATUS radar MISSING')
    print('STATUS scripts %d' % len([f for f in os.listdir(P['scripts']) if f.endswith('.md')]))
    try:   # once a day: is there a newer Script Studio? (update.py caches the answer in the state folder)
        import update
        line = update.check(ST)
        if line and 'AVAILABLE' in line:
            print(line)
    except Exception:
        pass
    print('STATE %s' % ST)


def cmd_where(a):
    apply_scripts_dir()
    for k in ('profile', 'about', 'voice', 'hookbank', 'taste', 'library', 'research', 'ideas', 'scripts'):
        print('%-9s %s' % (k, P[k]))


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(prog='ss.py')
    sp = ap.add_subparsers(dest='cmd', required=True)
    sp.add_parser('check')
    sp.add_parser('where')
    k = sp.add_parser('key')
    k.add_argument('--clipboard', action='store_true')
    pr = sp.add_parser('profile')
    pr.add_argument('action', choices=['show', 'set'])
    pr.add_argument('--handle')
    for f in ('niche', 'name', 'goal', 'offer', 'cta', 'scripts-dir', 'website', 'lang', 'competitors', 'subreddits', 'x-handles', 'x-search', 'sites', 'vocab'):
        pr.add_argument('--' + f, dest=f.replace('-', '_'))
    pr.add_argument('--add', action='store_true')
    pr.add_argument('--remove', action='store_true')
    s = sp.add_parser('scrape')
    s.add_argument('who')
    s.add_argument('--limit', type=int, default=40)
    s.add_argument('--since')
    s.add_argument('--max-usd', type=float, default=1.5)
    t = sp.add_parser('transcribe')
    t.add_argument('--own-top', type=int, default=10)
    t.add_argument('--own-bottom', type=int, default=4)
    t.add_argument('--per-creator', type=int, default=4)
    t.add_argument('--min-x', type=float, default=2.5)
    t.add_argument('--model', default='small.en')
    t.add_argument('--codes', help='only these reels (short codes or links)')
    r = sp.add_parser('reddit')
    r.add_argument('--subs')
    r.add_argument('--period', default='week', choices=['day', 'week', 'month', 'year', 'all'])
    r.add_argument('--limit', type=int, default=12)
    r.add_argument('--comments', type=int, default=1)
    x = sp.add_parser('x')
    x.add_argument('--handles')
    x.add_argument('--search')
    x.add_argument('--max', type=int, default=80)
    x.add_argument('--days', type=int, default=14)
    b = sp.add_parser('brief')
    b.add_argument('--days', type=int, default=120)
    qk = sp.add_parser('quick')
    qk.add_argument('--since', default='10 days')
    qk.add_argument('--limit', type=int, default=12)
    qk.add_argument('--own-top', type=int, default=10)
    qk.add_argument('--min-x', type=float, default=2.5)
    ix = sp.add_parser('import-x')
    ix.add_argument('source')
    im = sp.add_parser('import')
    im.add_argument('source')
    lb = sp.add_parser('library')
    lb.add_argument('--handle')
    lb.add_argument('--top', type=int, default=15)
    a = ap.parse_args()
    {'check': cmd_check, 'where': cmd_where, 'key': cmd_key, 'profile': cmd_profile, 'scrape': cmd_scrape,
     'transcribe': cmd_transcribe, 'reddit': cmd_reddit, 'x': cmd_x, 'brief': cmd_brief, 'library': cmd_library, 'import': cmd_import, 'quick': cmd_quick, 'import-x': cmd_import_x}[a.cmd](a)


if __name__ == '__main__':
    main()
