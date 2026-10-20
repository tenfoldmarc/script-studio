# Research: running it, reading it, reporting it

## What each step collects

- `scrape own` / `scrape competitors` / `scrape "a,b"` / `scrape "<reel link>"`: public reels with views, likes,
  comments, length, caption, the newest comments, and the media addresses. Saved per account in `ST/library/<handle>/`.
  Each reel gets a multiplier: its views divided by that account's median views. Posts under 3 days old are marked
  fresh: their views are still climbing, so they never count as winners or flops yet.
- `transcribe`: downloads the audio of the picked reels, transcribes it on the buyer's computer, and saves two
  frames per reel (0.4 s and 2 s in). The frames show the on-screen hook text and what the viewer sees first.
  Look at them: a hook is often on screen, not spoken.
- `reddit`: the top threads of each subreddit (Reddit's own ranking for the week, month or year) with the post
  text, plus the top comments of the 2 busiest threads per subreddit. Reddit limits how fast anyone can read it:
  a `MISSING r/x (429)` line means try that one again later, not that it is wrong.
- `x`: recent posts from the X accounts in the profile and popular posts (50+ likes) for each search term.
- Websites and newsletters in `sites`: not scraped by a script. Fetch each yourself, newest items only, and treat
  them like radar: a topic, a fact to check, the words people use.
- `brief`: one file, `ST/research/brief.md`, that puts it together in the order you should read it. Re-run it after
  any new scrape, transcription or radar run.

## Choosing competitors (when the buyer asks for help)

Good: accounts in the same niche or one step over, posting reels weekly, with views that swing (some reels far
above their own average). Those swings are what we learn from. Also good: one or two creators outside the niche
whose format the buyer admires. Weak: giant celebrity accounts (every post does well, nothing stands out), dead
accounts, accounts that only post carousels or photos, private accounts.

## The Apify connector fallback

No key, but an Apify tool is connected in this Claude: call the actor `apify/instagram-reel-scraper` with
`{"username": ["handle1", "handle2"], "resultsLimit": 40}` (or reel links in `username`), wait until it finishes,
then `import <datasetId>`. Everything after that is the same.

## Reading the brief

Read it in full, top to bottom, before ideas. Then look at the frames of the top 5 own and top 5 competitor reels.
Keep notes for yourself (never shown as is):
- **Their own winners**: what do the top 3 share? Topic, hook mechanism, length, story or list, how fast the
  first payoff comes, the CTA. That pattern is the strongest signal there is.
- **Their flops**: what do the bottom ones share? Usually a declarative hook, a slow start, a topic their audience
  doesn't care about, or too long. That becomes an `avoid:` lesson in `ST/taste.md` once you see it twice.
- **Competitor outliers**: for each, the principle (`references/ideas.md`), the hook mechanism and surface
  (`references/hooks.md`). A 10x on a small account is real. A 1.5x on a huge account is noise.
- **Radar**: which questions and complaints repeat, the exact phrases people use, anything new this week.
- **Comments** under reels: the questions people ask are next week's topics.

## The research report (after setup, and when they ask "what works")

Plain words, no tables of numbers, under 250 words. Specific, with links. Shape:

1. "Your account in one line": their median views, and the one pattern behind their best reels.
2. "Your best 3": each as one line: what it was, how far above their average, and why it worked.
3. "What's not working": one or two lines, honest and kind.
4. "What's winning around you": the 3 strongest competitor outliers, one line each, what to learn from it.
5. "What your audience is talking about": 2 or 3 radar topics.
6. "So here's the plan": the 2 or 3 directions the next scripts will push, then offer tomorrow's reel.

Never invent a reason a reel worked that the transcript, frames or numbers don't show. Say "probably" when it is a
read, not a fact.
