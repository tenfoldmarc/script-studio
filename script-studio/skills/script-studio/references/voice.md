# Voice: build the profile, then gate every script

A script that sounds like a copywriter wrote it fails even when the structure is perfect. Viewers can tell within one line. This file covers two jobs:

1. Build the buyer's voice profile from their own transcripts, then write it to `<state>/voice.md`.
2. Run the VOICE GATE on every script, hook, and caption before the buyer sees it.

Read the buyer's `voice.md` fresh before every script. Never write from memory of it.

---

## Part 1. Build the voice profile

### When to build or rebuild

- At setup, once their reels are scraped and transcribed.
- When the buyer says "update my voice" or "that doesn't sound like me" twice in a row.
- About every 30 days, or after 15 or more new reels, whichever comes first. Rebuilds merge into the existing file. They never wipe confirmed lines.

### Pick the calibration set

Ranked by multiplier (views divided by the buyer's own median), never raw views:

- **Top reels:** 1.2x or more of their median, up to 8. They show what their audience rewards.
- **3 to 5 typical reels:** 0.7x to 1.2x. They show the natural baseline voice. Without them you can't tell voice from hook luck. A phrase that shows up in top AND typical reels is voice. A phrase only in one viral reel is probably the topic. If too few typical ones are transcribed, `transcribe --codes "<links>"` for more.

Never count reels flagged fresh, trial or repeat. Skip reels where someone else does most of the talking (collabs, interviews, stitches), music-only or text-only posts, and trend audio lip-syncs. If fewer than 5 reels qualify as top, use what exists, set `status: thin`, and tell the buyer scripts will lean generic until more reels exist. Offer a fallback: they paste 3 to 5 voice notes or captions they wrote themselves.

Transcripts come from speech-to-text, and it mishears names and keywords (the brand, the product, the CTA keyword, platform names) even with their vocab list. Misheard words are not tics. Correct obvious mishearings in your notes, never copy a misheard word into a script, and when a frame shows the real word, trust the frame.

### What to extract

Work through every dimension. Back every claim with a real quote and a count ("4 of 12 reels"). No quote, no claim.

| Dimension | What to look for | How to measure |
|---|---|---|
| Openers | The first 1 to 2 sentences of every reel. Question, bold claim, mid-story, callout, reaction? | List them all. Tag each with a hook mechanism from `hooks.md`. Note which ones sit in top reels vs average ones. |
| Signature phrases | Lines they repeat on purpose ("let's get into it", "here's what nobody tells new agents") | 3+ reels = signature. 2 reels = likely. 1 reel = don't list. |
| Rhythm | One-word punches, repeats for emphasis, how often they stop short | Describe with quotes. No sentence-length stats: the transcriber runs sentences together. |
| Pace | Fast and dense, or slow with pauses | Words per second per format: transcript word count divided by reel duration, averaged separately for list or demo reels and for talking reels. Scripts use the pace of their format. |
| Energy | Starts at peak or builds, calm teacher, hype, deadpan | Describe in one line with an example. |
| Swearing | Yes or no, which words, how often, what job (emphasis, humor, frustration) | Count per 100 words. Zero found means a clean voice. Never add swearing to a clean voice. Never exceed the observed rate. |
| Humor | Self-deprecating, sarcastic, absurd exaggeration, dry, none | Quote 2 examples or write "none observed". |
| Viewer address | "you", "you guys", "y'all", "friend", "mama", "bro", a group name, or no direct address. Heavy "I" or "we"? | Count the main term. Use only that term in scripts. |
| Words they never use | Corporate and AI words absent from every transcript, jargon level | Check the sweep list in Part 2 plus niche jargon. Absence across 10+ reels is a strong signal. |
| Hook types they lean on | Which mechanisms show up most, which ones over-index in top reels | A mechanism that is 3 of their top 5 is their house hook. |
| House structure | How their best reels are built: seconds to first payoff, story or list, number of stages, CTA position, length | Map their top 3 by multiplier. If 2 of 3 share a shape, that's the template for `scripting.md`. |
| Pillars | The 3 to 5 topic clusters their winners keep returning to, plus their offer from `about.md` | One line and one proof reel each. |
| CTA style | How they phrase the ask, and whether they use a double close (the CTA plus a follow line) | Quote it. The ask and keyword themselves live in `about.md`; scripts say them in this wording. |
| Fillers and tics | "okay so", "listen", "right?", "literally", "like", "honestly" | Split into keep and cut (rules below). |
| Stories and proof | Real numbers, results, clients, credentials, life events they have said on camera | Copy each with its source reel. This is the on-camera proof bank. Facts they told you live in the proof bank in `about.md`. |
| Recurring stances | Opinions they repeat ("open houses are dead", "you don't need a meal plan, you need a grocery list") | Useful for contrarian ideas. Quote and count. |

### Fillers: keep vs cut

- **Keep** tics that carry personality, appear in top reels, and help the line land: a signature "okay so" opener, a "right?" check-in, a "listen" before the punchline.
- **Cut** stalls and noise: "um", "uh", false starts, doubled words ("like, like"), "you know what I mean" used as a pause, and anything that looks like transcription garbage.
- **Density cap:** a script may use kept tics at the rate they appear in the top reels, never more. Two "literally"s in a 30 second script is usually the ceiling even for heavy users. Overdoing a tic reads as parody.

### Confirmed vs inferred

Tag every line in the profile:

- `[inferred 6/12]` came from transcripts. The fraction is how many reels showed it.
- `[confirmed]` the buyer stated it or approved it. Confirmed lines are hard rules or strong targets.

Their setup answers (swearing yes or no, words and phrases they never say, things they never do) go in as `[confirmed]` hard rules. Show the 5-line voice summary with the research report and let them correct it. No extra round of questions. Each correction becomes a `[confirmed]` line.

Only buyer-confirmed lines go under Hard rules. Never invent a hard rule. A `[confirmed]` hard rule beats a signature phrase: if a phrase they use breaks one (hype words vs "no fake hype"), the rule wins.

### Learning from edits

When the buyer edits a script before approving it, diff their version against yours. A change they make twice (cut a word, swap a phrase, shorten every hook) becomes a `[confirmed]` line in `voice.md`. Log the lesson in `taste.md` too, tagged `(buyer)` (see `ideas.md`).

### Output template for `<state>/voice.md`

Write exactly this structure. Keep it free of em dashes.

```markdown
---
type: voice-profile
handle: @<handle>
built: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
calibration_set: <N> reels (<top N> top, <typical N> typical)
own_median_views: <number>
pace_talking: <words per second>
pace_list_demo: <words per second>
status: thin | draft-inferred | confirmed
---

# Voice profile: @<handle>

## Voice in one paragraph
<3 sentences, specific and testable. "Short punchy lines, lots of one-word punches. Talks to
'you guys', swears only for emphasis at the turn, never hedges, opens mid-story." Not
"friendly and relatable.">

## Hard rules (confirmed only)
- <rule> [confirmed]
<A confirmed hard rule beats a signature phrase. If a phrase they use breaks one, the rule wins:
note the phrase here as banned.>

## Pillars
- <pillar>: <one line> | proof: <reel URL>, <multiplier>x [inferred or confirmed]
<3 to 5, inferred from their winners plus their offer in about.md>

## Sounds like / never sounds like
| Sounds like (real quote) | Never sounds like |
|---|---|
| "<quote>" (reel 3) | <the AI or corporate version of the same line> |
<6 to 8 rows>

## Openers
- "<real first line>" | <mechanism> | <views>, <multiplier>x [inferred]
<one per calibration reel>

## Signature phrases
- "<phrase>" | <how and where they use it> [inferred 4/12]

## Rhythm and pacing
- Pace, talking reels: <N> w/s | list or demo reels: <N> w/s
- <habits: one-word punches, repeats for emphasis, with quotes> [inferred]

## Energy
<one line + quote>

## Viewer address
- Main term: "<term>" [inferred N/N]
- I vs we: <pattern>

## Swearing
<rate per 100 words, words used, the job it does> or "Clean voice. No swearing." [inferred or confirmed]

## Humor
<type + 2 quotes> or "None observed."

## Fillers and tics
- Keep: "<tic>" (max <N> per script)
- Cut: <list>

## Vocabulary
- Uses: <words + quotes>
- Never uses: <words> [inferred 12/12 or confirmed]

## Hook types they lean on
- <mechanism>: <N> of top <N> | example: "<line>"

## House structure
<beat map of their best shape: hook type, seconds to first payoff, stages, story or list,
CTA position, typical length and word count>

## CTA style (the ask and keyword live in about.md)
- Wording: "<exact wording>" [inferred or confirmed]
- Double close (CTA plus a follow line): yes or no [inferred N/N]

## Proof bank (said on camera; told-me facts live in about.md)
- <fact> | said in <reel URL>

## Recurring stances
- "<stance>" [inferred 3/12]

## Sample lines (the target sound)
<8 to 12 verbatim lines from top reels, one per line>

## Calibration set
| # | URL | Views | Multiplier | Top or typical | What makes it them |
|---|---|---|---|---|---|

## Changelog
- <YYYY-MM-DD>: <what changed and why>
```

---

## Part 2. The VOICE GATE

Run this on every script, every hook option, every on-screen line, and every caption before showing anything. Show only the post-gate version. Never show the draft that failed.

### Step 1. Line-by-line match

Score every spoken line, plus the on-screen text and the caption's first line, against the voice file:

- **Match**: could sit in one of their reels unchanged. Rhythm, words, and address term all fit.
- **Close**: right idea, one thing off (a word they'd never pick, a sentence too long, a tic missing or overused).
- **Miss**: sounds like a different person.

Rules:
- Rewrite every Miss, then re-score it.
- 3 or more Close lines with the same problem means a pattern: sweep the whole script for it.
- Pass = zero Miss and no more than 1 Close in 5 lines.

Quick example, for a calm, clean-voiced personal trainer who says "friend":

| Line | Score | Fix |
|---|---|---|
| "Friend, your knees aren't the problem." | Match | |
| "This revolutionary approach will transform your mobility." | Miss | "This takes four minutes and you can do it in your kitchen." |
| "So basically, the thing is, you've been stretching wrong." | Close (stacked filler, not their tics) | "You've been stretching the wrong muscle." |

### Step 2. Hard rules

Every `[confirmed]` hard rule in `voice.md` and every line under "Never do or say" in `about.md` is blocking. A violation means the script does not ship until fixed, even when the line is one of their signature phrases. If both are empty, there are no extra constraints. Don't invent any.

### Step 3. AI-tell sweep

Zero tolerance on the content surfaces (spoken lines, on-screen text, caption, title). A phrase on the buyer's signature list is exempt, once per script, unless it breaks a hard rule.

**Punctuation**
- Em dashes, and spaced hyphens or en dashes used as dashes. Use a period, a comma, or a line break.
- Semicolons in spoken lines. Nobody speaks a semicolon.
- Curly quotes in the output file. Use straight quotes.

**Openers and transitions to kill**
"Here's the thing", "Let me break this down", "Let me explain", "In this video", "Hey guys, welcome back", "What if I told you", "The truth is", "Let's dive in", "Picture this", "Imagine this", "Let that sink in", "Here's the kicker", "The best part?", "But wait, there's more", "Moreover", "Additionally", "Furthermore", "In other words", "To put it simply", "At the end of the day", "It's worth noting", "In today's fast-paced world", "Without further ado", "Buckle up".

**Words to kill** (unless the transcripts prove they say them)
delve, leverage, utilize, unlock, unleash, game-changer, game-changing, seamless, robust, elevate, empower, transform/transformative, revolutionize, supercharge, harness, navigate (figurative), journey (figurative), landscape, realm, tapestry, testament, crucial, pivotal, vital, cutting-edge, next level, synergy, holistic, curated, boost (as filler), "deep dive", "secret sauce", "hack" (when it isn't one).

**Structural tells**
- **Negative parallelism overuse.** "It's not X, it's Y" / "That's not a diet. That's a lifestyle." Allowed once per script, only as a deliberate contrast beat. Twice is an AI tell.
- **Rule-of-three padding.** Triplets of adjectives or benefits ("faster, cheaper, and easier"), three parallel sentences with the same shape. Keep a three only when there are truly three items. Otherwise use two, or one.
- **Staccato stacks.** "No fluff. No filler. Just results." Three short fragments in a row reads as ad copy. Real speech clusters messier.
- **Fake question reveals.** "The result? Double the leads." "The secret? Consistency." One per script at most.
- **Colon setups.** "Here's what happened:" before every point.
- **-ing tack-ons.** "...helping you save time, ensuring you never miss a call."
- **Synonym cycling.** Calling the same thing "clients", then "customers", then "buyers" to avoid repetition. Say the same word again.
- **Symmetry.** Every section the same length, every sentence the same length. Vary it.
- **Generic closers.** "And that's the power of meal prep." "The choice is yours." "Your future self will thank you."
- **Hedging.** "might potentially", "could arguably". Take the stance or put the nuance in the caption.
- **Vague authority.** "Studies show", "experts say". Name the source with `[VERIFY: source]` or cut it.
- **Manipulative teases.** "Stay till the end", "the last one will shock you", "you won't believe #3".
- **Motivational filler.** "You deserve this", "Your time is now", "Believe in yourself".

A fast first pass on the spoken script section catches the mechanical ones (it skips markdown list markers):

```bash
perl -CSD -ne '$s=1 if /^## Spoken script/; $s=0 if /^## (?!Spoken script)/; next unless $s; s/^\s*(?:[-*+]|\d+\.)\s+//; print "$.: $_" if /[\x{2014}\x{2013}\x{201C}\x{201D}\x{2018}\x{2019}]| - |;|delve|leverage|utiliz|unlock|unleash|transform|game.?chang|seamless|robust|elevat|empower|next level|here.s the thing|here.s the kicker|what if i told you|buckle up|let me break|in this video|the truth is|let.s dive|it.s not .*, it.s/i' "<script-file>"
```

Then read the spoken lines by eye for the structural tells (grep can't see rhythm), and the on-screen text, caption and hook options for the whole list.

### Step 4. Read-aloud test

Read every line at the buyer's pace for this script's format (talking, or list or demo).

- **Breath test.** Any line that can't be said in one breath (roughly 15 words) gets split.
- **Mouth test.** Tongue-twisters, stacked consonants, and words they'd stumble on get swapped.
- **Numbers.** Spoken lines use numbers the way they'd say them ("forty grand", "like 3 in the morning"). On-screen text uses digits ("$40K", "3AM").
- **Blog check.** If it sounds like an article read aloud rather than a person talking to one friend, it fails. Rewrite with shorter sentences, more "you", fewer connectors.

### Step 5. No invented facts: `[VERIFY: ...]`

Never invent a number, name, date, client, result, price, quote, study, or personal story. Use a placeholder that tells the buyer exactly what to fill:

- `[VERIFY: how many listings you sold in your first year]`
- `[VERIFY: the client's first name, or say "a client"]`
- `[VERIFY: the actual price of the cheaper option]`

Safe without a placeholder: facts from the proof banks (`voice.md` for what they said on camera, `about.md` for what they told you), facts the buyer said in this chat, and widely known facts in their field. List widely known facts, and proof bank lines marked "check before filming", under "Before you film" so they can check.

**No biography laundering.** A competitor's story stays theirs. Never turn "I lost 40 pounds" from a source reel into a first-person claim for the buyer. Either attribute it ("a trainer I follow lost...") or swap in a `[VERIFY: your own version of this story]`.

A script with `[VERIFY]` slots can still be shown. List every slot under "Before you film" at the bottom of the script so nothing gets recorded as a placeholder.

### Gate report

End every script with a short gate report:

```
Voice gate: 15 Match, 2 Close, 0 Miss | Hard rules: pass | Sweep: clean | Read-aloud: pass | VERIFY: 2 slots
```

If anything blocking survives (a Miss, a broken hard rule, a banned phrase you couldn't remove), say so plainly and say what to fix. Never mark a script as passing with a flag still open.
