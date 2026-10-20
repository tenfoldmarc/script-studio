---
name: script-studio
description: "Script Studio (Creator Studio add-on). Studies the creator's own Instagram reels and their competitors' (scraped, ranked against each account's own average, transcribed), plus the places their audience hangs out (Reddit, X, websites), then writes ready-to-record short-form scripts in the creator's own voice, built on hooks and topics that already won. Use when the user says 'give me tomorrow's reel', 'give me ideas', 'what should I film', 'write me a script', 'script about X', 'what should I post', 'give me reel ideas', 'a week of scripts', 'make my version of this reel <link>', 'research my competitors', 'what are my best hooks', 'what works on my account', 'refresh my research', 'add a competitor', 'add a source', 'open my dashboard', 'show me my hooks', 'show my competitors', 'set up Script Studio', or runs /script-studio."
---

# Script Studio

Research in, ready-to-record scripts out. The creator films, Creator Studio edits.

`SS` is this skill's folder (`${CLAUDE_SKILL_DIR}`, or the base directory Claude Code gave you when it loaded the
skill). It is read-only: never write into it. `PY` is the Python the quiet check prints. `ST` is the buyer's
Script Studio folder (the `STATE` line): everything about them lives there and survives updates.

Every command below is `PY "SS/scripts/ss.py" <command>`. Talk to the buyer in plain words: never show them STATUS
lines, JSON, command lines or this skill's file names. Their own scripts folder is fine to name.

Read before writing anything for the buyer, every chat, fresh (never from memory):
- `references/ideas.md` before ideas, `references/scripting.md` before a script, `references/hooks.md` before hooks
  or the hook bank, `references/voice.md` before building their voice and before showing any script (the VOICE GATE).
- `references/research.md` before running or reading research. `references/dashboard.md` before building or
  restyling their dashboard.

## What wins, highest first
1. What the buyer asks for in this chat.
2. `ST/about.md`, their `[confirmed]` lines in `ST/voice.md`, and the `(buyer)` lessons in `ST/taste.md`.
3. Their own winners (1.5x or more of their own median, settled, not fresh) and the `(research)` lessons in `ST/taste.md`.
4. Competitor outliers and the topic radar.
5. The defaults in the references. A default never beats anything above it.

## Step 0: the quiet check (every chat)

Mac and Linux: `sh "SS/scripts/start.sh"`. Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "SS/scripts/start.ps1"`.
It prints `PY <path>` then STATUS lines. Read them, do not announce them.

- `SETUP running the Creator Studio setup first`: say once that the first run takes a few minutes, then wait.
- `STATUS studio NOT_INSTALLED` or `SETUP_FAILED`: Script Studio runs on Creator Studio. Say: "Script Studio
  needs Creator Studio installed first. Install it from your portal, then say 'set up Script Studio'." Stop.
- `STATUS profile MISSING`: the setup below, then what they asked for.
- Half-finished setup: resume at the first missing piece, in this order: profile, key (`apify MISSING` or
  `INVALID`: setup round b), research (`research MISSING`: Refresh), about (`about MISSING` with profile OK: ask the
  round c questions and write `ST/about.md`), voice (`voice MISSING` with research present: setup step 5). Never
  restart the setup and never re-ask what is already saved.
- `STATUS research STALE` (7 days or more): offer one line, "Want me to refresh your research first? About 10
  minutes, I'll write while it runs." On yes start the refresh in the background (see Refresh) and keep going with
  what is there.
- `STATUS competitors MISSING <handles>`: those accounts were never scraped. Scrape just those in the background
  (`scrape "<handles>"`, then `transcribe` and `brief`) as a small refresh. If one still fails, tell the buyer in
  one line: the account is private or the handle is wrong.
- `STATUS radar <N> days old` or `STATUS radar MISSING`: see the radar rule under Refresh.

## The setup (first time only)

They came for scripts, so keep it tight. Three short rounds from them, then you do the work.

1. Say: "Welcome to Script Studio. Quick one-time setup: I'm going to study your account, your competitors and the
   places your audience hangs out, so every script is built on what already works. Then I write them in your voice."
2. Round a, the basics, in ONE message:
   - their Instagram handle
   - in one or two lines: what they do, who it is for, and what they sell (or want to sell)
   - 3 to 10 accounts whose reels pop in their space (competitors, or creators they wish they were). "Not sure?
     Tell me your niche and I'll find some." If they want help: search the web for creators in that niche, propose
     6 to 8 with a line each, let them cut.
   - their website (or link-in-bio page), so their research dashboard matches their brand
   - where I should look for video ideas: the places their audience hangs out and the sources they follow.
     Subreddits, X accounts, topics to search on X, newsletters, blogs, news sites, YouTube channels. "A few is
     plenty, and you can add more any time." Websites, newsletters and YouTube channels go in `--sites`.
   - 3 to 10 words the transcriber might mishear: their brand, product names, the keyword they ask people to comment.
   - where finished scripts should be saved (default `~/Documents/Script Studio`).
   If they name no sources, suggest 3 to 5 that fit their niche (search the web) and let them cut.
   Save it: `profile set --handle "<h>" --niche "<one line>" --competitors "a,b,c" --subreddits "a,b"
   --x-handles "a,b" --x-search "term one;term two" --sites "url,url" --vocab "a,b,c" --website "<url>" --scripts-dir "<folder>"`.
   The profile holds only the handle, niche, accounts and sources. What they sell goes into `ST/about.md` (step 4).
3. Round b, the Apify key (Apify is the service that collects public reels; the free plan includes $5 of credit a
   month and a full research run uses well under $1 of it). Say:
   > "Next. Make a free account at apify.com (Google sign-in works). Then open Settings, then API &
   > Integrations, and click the copy button next to your Personal API token. Don't paste it here: just copy it
   > and tell me 'copied'."
   On "copied": `key --clipboard`. `KEY saved`: go on. `KEY NOT_FOUND`: the clipboard had something else, ask them
   to copy it again. `KEY INVALID`: the token is wrong or revoked, ask them to copy it again from the same page.
   If they paste it in the chat anyway: save it with `key` reading it from stdin (`printf '%s' '<token>' | PY ...
   key`), never echo it back, and say it is saved.
   No key at all but an Apify tool is connected in this Claude: you may run `apify/instagram-reel-scraper` through
   that tool (input as in `references/research.md`) and pass the dataset id to `import <id>`.
4. Round c, while the research runs: start the first full research (see Refresh, all steps, `reddit --period
   month`). Tell them: "Studying your reels and your competitors now. About 10 to 15 minutes. While that runs, four
   quick questions." Ask in ONE message:
   - What is the one goal for your content right now (followers, leads, sales of X, authority)?
   - What should every reel ask people to do (comment a word, follow, DM, link in bio)? Any keyword you use?
   - Do you swear on camera (yes or no)? Any word or phrase you never say? Anything you never do or touch on camera
     (topics, claims, brands)?
   - Stories and proof you can use: results, numbers, client wins, your own story. A few lines is plenty.
   Write `ST/about.md`, the only home for their goal, offer and CTA:
   ```markdown
   # About @<handle>
   ## Goal
   ## Offer
   ## Audience
   ## CTA + keyword
   ## Never do or say
   ## Proof bank
   - <fact> | told me <YYYY-MM-DD>, or <file name> (check before filming)
   ```
   Their swearing answer and never-do-or-say list also go into `ST/voice.md` as `[confirmed]` hard rules (step 5).
   Facts about their own product from files on their computer, or from the offer above, may go into the proof bank
   with a "check before filming" note.
5. When transcripts are in: build `ST/voice.md` exactly as `references/voice.md` Part 1 says, seed `ST/hook-bank.md`
   from the competitor and own outliers (`references/hooks.md`), and create `ST/taste.md` with its header
   (`references/ideas.md`).
6. Build their dashboard: fill `ST/brand.json` from their website (`references/dashboard.md`), then
   `PY "SS/scripts/dashboard.py" --open`. One line: "Your research dashboard is open: your best reels, your hook
   library, your competitors and the topics. Say 'open my dashboard' any time."
   Then give them the research report (`references/research.md`, "The research report") with the 5-line voice summary
   under it, and let them correct either. No extra round of questions.
7. Straight into what they asked for. If they asked for nothing yet: "Want tomorrow's reel?" and go.

A buyer who asks for the setup again ("set up Script Studio again", "change my competitors"): `profile show`, say
what they have in two plain lines, change only what they ask (`profile set --competitors "x" --add` or `--remove`;
goal, offer and CTA changes go in `ST/about.md`). Never delete their voice, hook bank, taste file or scripts.

## Refresh (the research)

Full refresh, in this order. Long steps run in the background; tell the buyer what is happening in one line.
1. `scrape own --limit 50`
2. `scrape competitors --limit 40` (skip if they have none)
3. `transcribe` in the background (picks their top 10, weakest 4, two typical ones, and up to 4 outliers per
   competitor; skips anything already done). `EXPIRED` lines: run the scrape for those accounts again, then
   `transcribe` again.
4. `reddit --period month` in the background if they have subreddits (it is slow, a few minutes, because Reddit
   rate-limits), `x` if they have X accounts or searches.
5. `brief`, then read `ST/research/brief.md` in full, and look at the frame images it lists for on-screen hook text.
6. Update the hook bank with new outliers, note new winners and flops in `ST/voice.md` (House structure, Hook types
   they lean on, Pillars) and tell them in two or three lines what changed since last time.
7. Rebuild the dashboard: `PY "SS/scripts/dashboard.py"` (add `--open` only if they asked to see it).

## Fresh research for every ideas ask

Every time they ask for ideas or tomorrow's reel, research first, so the ideas come from what is happening now:
1. Say one line: "Checking what's new on your account, your competitors and your sources. Two or three minutes."
2. Start `reddit --period week` in the background (if they have subreddits; skip it if it ran in the last 12 hours).
3. Run `quick`: the newest reels of their account and every competitor in one cheap run, transcripts of any new
   outliers, X, then the brief. About $0.10 to $0.30 of Apify credit.
4. While those run, fetch each of their `sites` yourself, newest items only (newsletters, blogs, news, YouTube
   channel pages): note titles, dates and the angle.
5. When Reddit finishes, `brief` again, read it, then write the cards. If Reddit is still running after 5 minutes,
   go on without it and say so in one line.
Skip steps 2 to 4 only when they ran in this chat already, or the buyer says "skip the research".

## Tomorrow's reel (the main job)

Triggers: "give me tomorrow's reel", "what should I post", "reel ideas", "write me a script" with no topic.
1. Quiet check, then fresh research (above), then read `ST/research/brief.md`.
2. Read `ST/taste.md`, `ST/voice.md`, `ST/about.md`, `ST/hook-bank.md`.
3. Write 5 idea cards (`references/ideas.md`), run its 7-point check, and save the full cards to
   `ST/ideas/YYYY-MM-DD ideas.md`. Show them short: the working title, one line on why it should win (the proof:
   whose reel, how far above their average, or the thread), the pillar. Ask which.
4. They pick (or mix two, or give their own angle). Before writing, read their last 10 scripts in their scripts
   folder (the ones `ST/taste.md` logs as approved or edited count most; their own edits show how they really
   talk) and the transcripts of their top 3 reels. Match how they speak. Scripts are for you to learn from: never
   put them in the dashboard. Write the script (`references/scripting.md`) with 10 hook
   options ranked (`references/hooks.md`), #1 in the script. Run the VOICE GATE.
5. Save it to their scripts folder (`where` prints it) as `YYYY-MM-DD <title>.md`: today's date, and strip
   `/ \ : * ? " < > |` from the title. Use the output format from `references/scripting.md`, all 10 hooks included.
6. Show the script, then the top 3 hooks (one line each) and say the other 7 are in the file. Say where it is saved
   in one line. Ask one thing: "Want me to change anything, or is this the one?"
7. On approval: "Film it, drop the clips in, and say 'edit it'. Creator Studio will edit the reel."
   Every approval, edit or rejection gets logged in `ST/taste.md`; edits they make twice become `[confirmed]` lines
   in `ST/voice.md` (`references/voice.md`).

## Other asks

- **"Script about X"** (their topic): skip the cards. Read the brief and hook bank anyway: use the closest proven
  hook mechanism and their own best structure for that kind of topic. Same output, gate, save and steps 6 to 7.
- **"Transcribe this reel <link>"**: `scrape "<link>"`, `transcribe --codes "<link>"`, then show the transcript and what its hook does.
- **"Make my version of this reel <link>"**: `scrape "<link>"`, then `transcribe --codes "<link>"`, read its
  transcript and frames. Find the principle (`references/ideas.md`), bend it 70/30 to them, write the script. Never
  copy their lines; name the source in the card so the buyer knows where it came from.
- **"A week of scripts" / "5 scripts"**: one round of 8 to 10 cards (saved to the ideas file), they pick 5 (or you
  pick the 5 strongest with different pillars, mechanisms and sources), then the scripts one after another. Save each.
- **"What are my best hooks" / "what works on my account" / "show my competitors"**: `PY "SS/scripts/dashboard.py"
  --open`, then two or three lines on what stands out. The research report if they want it in the chat.
- **"Open my dashboard"**: `PY "SS/scripts/dashboard.py" --open`. **"Make my dashboard match my brand"**: redo
  `ST/brand.json` (`references/dashboard.md`), then rebuild with `--open`.
- **"Add a source" / "check X for ideas"**: `profile set --sites "<url>" --add` (or `--subreddits`, `--x-handles`,
  `--x-search`), then use it in the next research.
- **"Research my competitors" / "add a competitor"**: update the profile, scrape just those (`scrape "a,b"`),
  `transcribe`, then report the outliers and what each one teaches.
- **"Turn this script into a carousel"**: hand the finished script to the carousel side of Creator Studio
  ("make a carousel from this script").

## Costs and limits (say only when asked, or before anything unusual)
- A full refresh costs about $0.50 to $1 of Apify credit (each scrape prints its ceiling as `PLAN ... at most`).
  Apify's free plan includes $5 a month. Never run more than one full refresh a day unless they ask.
- Reels only (Instagram) in this version. Private accounts can't be studied.
- Transcription runs on their computer for free. About 10 to 20 seconds a reel.
