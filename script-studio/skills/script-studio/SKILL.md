---
name: script-studio
description: "Script Studio (Claude Creator Studio add-on). Studies the creator's own Instagram reels and their competitors' (scraped, ranked against each account's own average, transcribed), plus the places their audience hangs out (Reddit, X, websites), then writes ready-to-record short-form scripts in the creator's own voice, built on hooks and topics that already won. Use when the user says 'give me tomorrow's reel', 'write me a script', 'script about X', 'what should I post', 'give me reel ideas', 'a week of scripts', 'make my version of this reel <link>', 'research my competitors', 'what are my best hooks', 'what works on my account', 'refresh my research', 'add a competitor', 'set up Script Studio', or runs /script-studio."
---

# Script Studio

Research in, ready-to-record scripts out. The creator films, Claude Creator Studio edits.

`SS` is this skill's folder (`${CLAUDE_SKILL_DIR}`, or the base directory Claude Code gave you when it loaded the
skill). It is read-only: never write into it. `PY` is the Python the quiet check prints. `ST` is the buyer's
Script Studio folder (the `STATE` line): everything about them lives there and survives updates.

Every command below is `PY "SS/scripts/ss.py" <command>`. Talk to the buyer in plain words: never show them STATUS
lines, JSON, command lines or this skill's file names. Their own scripts folder is fine to name.

Read before writing anything for the buyer, every chat, fresh (never from memory):
- `references/ideas.md` before ideas, `references/scripting.md` before a script, `references/hooks.md` before hooks
  or the hook bank, `references/voice.md` before building their voice and before showing any script (the VOICE GATE).
- `references/research.md` before running or reading research.

## What wins, highest first
1. What the buyer asks for in this chat.
2. Their `[confirmed]` lines in `ST/voice.md` and every lesson in `ST/taste.md`.
3. Their own winners (their reels that beat their own average).
4. Competitor outliers and the topic radar.
5. The defaults in the references. A default never beats anything above it.

## Step 0: the quiet check (every chat)

Mac and Linux: `sh "SS/scripts/start.sh"`. Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "SS/scripts/start.ps1"`.
It prints `PY <path>` then STATUS lines. Read them, do not announce them.

- `SETUP running the Creator Studio setup first`: say once that the first run takes a few minutes, then wait.
- `STATUS studio NOT_INSTALLED` or `SETUP_FAILED`: Script Studio runs on Claude Creator Studio. Say: "Script Studio
  needs Claude Creator Studio installed first. Install it from your portal, then say 'set up Script Studio'." Stop.
- `STATUS profile MISSING`: the setup below, then what they asked for.
- `STATUS apify MISSING` or `INVALID` (after setup): ask for the key again (setup step 3) before any research.
- `STATUS voice MISSING` with research present: build the voice now (setup step 5), then go on.
- `STATUS research STALE` (7 days or more): offer one line, "Want me to refresh your research first? About 10
  minutes, I'll write while it runs." On yes start the refresh in the background (see Refresh) and keep going with
  what is there.

## The setup (first time only)

They came for scripts, so keep it tight. Two messages from them, then you do the work.

1. Say: "Welcome to Script Studio. Quick one-time setup: I'm going to study your account, your competitors and the
   places your audience hangs out, so every script is built on what already works. Then I write them in your voice."
2. Ask in ONE message:
   - their Instagram handle
   - in one or two lines: what they do, who it is for, and what they sell (or want to sell)
   - 3 to 10 accounts whose reels pop in their space (competitors, or creators they wish they were). "Not sure?
     Tell me your niche and I'll find some." If they want help: search the web for creators in that niche, propose
     6 to 8 with a line each, let them cut.
   - where their audience hangs out: subreddits, X accounts or topics, newsletters or websites. Optional.
   - where finished scripts should be saved (default `~/Documents/Script Studio`).
   Save it: `profile set --handle "<h>" --niche "<one line>" --offer "<what they sell>" --competitors "a,b,c"
   --subreddits "a,b" --x-handles "a,b" --x-search "term one;term two" --sites "url,url" --scripts-dir "<folder>"`.
3. The Apify key (Apify is the service that collects public reels; the free plan includes $5 of credit a month and a
   full research run uses well under $1 of it). Say:
   > "Last thing. Make a free account at apify.com (Google sign-in works). Then open Settings, then API &
   > Integrations, and click the copy button next to your Personal API token. Don't paste it here: just copy it
   > and tell me 'copied'."
   On "copied": `key --clipboard`. `KEY saved`: go on. `KEY NOT_FOUND`: the clipboard had something else, ask them
   to copy it again. `KEY INVALID`: the token is wrong or revoked, ask them to copy it again from the same page.
   If they paste it in the chat anyway: save it with `key` reading it from stdin (`printf '%s' '<token>' | PY ...
   key`), never echo it back, and say it is saved.
   No key at all but an Apify tool is connected in this Claude: you may run `apify/instagram-reel-scraper` through
   that tool (input as in `references/research.md`) and pass the dataset id to `import <id>`.
4. Research: run the first full research (see Refresh, all steps). Tell them: "Studying your reels and your
   competitors now. About 10 to 15 minutes. While that runs, four quick questions." Ask in ONE message:
   - What is the one goal for your content right now (followers, leads, sales of X, authority)?
   - What should every reel ask people to do (comment a word, follow, DM, link in bio)? Any keyword you use?
   - Anything you never say or never do on camera (swearing, topics, claims, brands)?
   - Stories and proof you can use: results, numbers, client wins, your own story. A few lines is plenty.
   Save their answers into `ST/about.md` (goal, offer, audience, CTA, never-do list, proof) and the `[confirmed]`
   parts into the voice file in the next step.
5. When transcripts are in: build `ST/voice.md` exactly as `references/voice.md` Part 1 says, seed `ST/hook-bank.md`
   from the competitor and own outliers (`references/hooks.md`), and create `ST/taste.md` with its header
   (`references/ideas.md`).
6. Give them the research report (`references/research.md`, "The research report"). Short, specific, in plain words.
7. Straight into what they asked for. If they asked for nothing yet: "Want tomorrow's reel?" and go.

A buyer who asks for the setup again ("set up Script Studio again", "change my competitors"): `profile show`, say
what they have in two plain lines, change only what they ask (`profile set --competitors "x" --add` or `--remove`).
Never delete their voice, hook bank, taste file or scripts.

## Refresh (the research)

Full refresh, in this order. Long steps run in the background; tell the buyer what is happening in one line.
1. `scrape own --limit 50`
2. `scrape competitors --limit 40` (skip if they have none)
3. `transcribe` in the background (picks their top 10, weakest 4, two typical ones, and up to 4 outliers per
   competitor; skips anything already done). `EXPIRED` lines: run the scrape for those accounts again, then
   `transcribe` again.
4. `reddit` if they have subreddits, `x` if they have X accounts or searches.
5. `brief`, then read `ST/research/brief.md` in full, and look at the frame images it lists for on-screen hook text.
6. Update the hook bank with new outliers, note new winners and flops in `ST/voice.md` (House structure, Hook types
   they lean on) and tell them in two or three lines what changed since last time.

The radar alone (`reddit`, `x`, and fetching their `sites` yourself) is cheap and fast: run it at the start of any
ideas session when the newest radar file is older than 2 days.

## Tomorrow's reel (the main job)

Triggers: "give me tomorrow's reel", "what should I post", "reel ideas", "write me a script" with no topic.
1. Quiet check. Radar fresh (see above). `brief` if anything changed since the last one, then read it.
2. Read `ST/taste.md`, `ST/voice.md`, `ST/about.md`, `ST/hook-bank.md`.
3. Write 5 idea cards (`references/ideas.md`), run its 7-point check, show them short: the working title, one line
   on why it should win (the proof: whose reel, how far above their average, or the thread), the pillar. Ask which.
4. They pick (or mix two, or give their own angle). Write the script (`references/scripting.md`) with 10 hook options
   ranked (`references/hooks.md`), the top one in the script. Run the VOICE GATE. Then show it.
5. Save it to their scripts folder (`where` prints it) as `YYYY-MM-DD <title>.md`, in the output format from
   `references/scripting.md`. Tell them where it is in one line.
6. Ask one thing: "Want me to change anything, or is this the one?" Every approval, edit or rejection gets logged in
   `ST/taste.md`; edits they make twice become `[confirmed]` lines in `ST/voice.md` (`references/voice.md`).
7. End with: "Film it, drop the clips in, and say 'edit it'. Claude Creator Studio will edit the reel."

## Other asks

- **"Script about X"** (their topic): skip the cards. Read the brief and hook bank anyway: use the closest proven
  hook mechanism and their own best structure for that kind of topic. Same output, gate and save.
- **"Make my version of this reel <link>"**: `scrape "<link>"`, then `transcribe --codes "<link>"`, read its
  transcript and frames. Find the principle (`references/ideas.md`), bend it 70/30 to them, write the script. Never
  copy their lines; name the source in the card so the buyer knows where it came from.
- **"A week of scripts" / "5 scripts"**: one round of 8 to 10 cards, they pick 5 (or you pick the 5 strongest with
  different pillars, mechanisms and sources), then the scripts one after another. Save each.
- **"What are my best hooks" / "what works on my account"**: the research report, focused on their own account.
- **"Research my competitors" / "add a competitor"**: update the profile, scrape just those (`scrape "a,b"`),
  `transcribe`, then report the outliers and what each one teaches.
- **"Turn this script into a carousel"**: hand the finished script to the carousel side of Claude Creator Studio
  ("make a carousel from this script").

## Costs and limits (say only when asked, or before anything unusual)
- A full refresh costs about $0.50 to $1 of Apify credit (each scrape prints its ceiling as `PLAN ... at most`).
  Apify's free plan includes $5 a month. Never run more than one full refresh a day unless they ask.
- Reels only (Instagram) in this version. Private accounts can't be studied.
- Transcription runs on their computer for free. About 10 to 20 seconds a reel.
