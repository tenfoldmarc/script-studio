# The research dashboard

One page that shows the buyer their research in their own branding: their reels ranked against their usual, their
hook library, competitor breakouts and the topic radar. `PY "SS/scripts/dashboard.py"` writes it to `ST/dashboard/`:
- `index.html`: the fixed page (layout, brand colors and fonts, tabs, filters, search, the reel dialog). Written only
  the first time, when `ST/brand.json` or the logo changed, or with `--rebuild`.
- `data.js`: everything the page shows. Rewritten on every run. An open dashboard reloads it every 20 seconds and
  redraws itself in place, keeping the buyer's tab, filters, search and scroll, with a small "Updated just now" note.
- `img/`: reel pictures. Only new ones are fetched; ones the page no longer shows are removed.
It prints `DASHBOARD <path>` and then `UPDATED data` or `BUILT shell+data`. Never show those lines.

## When to run it
- First build, at the end of setup right after the research report: fill `ST/brand.json` first (below), then run
  it with `--open` and tell the buyer in one line, for example: "Your research dashboard is open in your browser.
  Keep it open: it updates itself every time we refresh."
- After every research run (full refresh or radar only, once `brief` has run), after any hook bank update, and
  after `ST/voice.md` changes its Pillars or Hook types: run it without `--open`. It only refreshes the data, and
  an open dashboard picks the change up by itself within 20 seconds, so never reopen it and never tell them to
  reload. One line is enough, for example: "Your dashboard has the new numbers."
- Whenever they ask: "show me my dashboard", "open my research", "what does my research look like": run it with
  `--open`.
- `--rebuild` only after a brand change (colors, fonts, logo) or if the page looks broken. A brand.json edit is
  picked up on its own anyway; `--rebuild` just forces it.
Never paste the file path unless they ask where it lives.

## Filling ST/brand.json (once, at setup)
```json
{"name": "Jane Doe", "colors": {"bg": "#1b2d28", "surface": "#223530", "text": "#f1eee4", "muted": "#b3ac98",
 "accent": "#328559", "accent2": "#67c191"}, "fonts": {"heading": "Bebas Neue", "body": "Inter"},
 "google_fonts_url": "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&display=swap",
 "logo": "brand/logo.png", "mode": "dark", "source": "https://janedoe.com"}
```
1. Find their site: the website they gave you, else the link in their Instagram bio (a link-in-bio page counts),
   else their Instagram profile itself. Ask once only if none of those exist.
2. Fetch the homepage HTML and its main stylesheet (the `<link rel="stylesheet">` files; with a built site the CSS
   holds everything). If the page is built by JavaScript and the HTML is empty, open it in the browser tools and
   read computed styles instead (`getComputedStyle` of `body`, `h1`, `h2`, the main buttons).
3. Colors, real ones only, never invented:
   - `bg`: the page background (`body` background, or `--background` style variables).
   - `surface`: their card or section color, or the bg nudged 4 to 6% lighter (dark) or darker (light).
   - `text`: the main heading or body text color. `muted`: their secondary text color.
   - `accent`: their main button color. Badges, the active tab and buttons use it, nothing else.
   - `accent2`: a second brand color they really use (links, highlights). None: a lighter (dark mode) or darker
     (light mode) tint of `accent` that reads as text on `bg`.
   - Shadcn/Tailwind sites store colors as `--primary: 148 45% 36%` (hue, saturation, lightness). Convert to hex.
4. Contrast: `text` on `bg` at least 4.5:1, `muted` on `surface` at least 4.5:1, `accent2` on `surface` at least
   4.5:1. Check the math before saving. The script also nudges anything below 4.5:1 and picks a readable label
   color for `accent` fills, but start from a set that already passes.
5. `mode`: `dark` if their site background is dark, `light` if it is light. Match the site, not your taste.
6. Fonts: the `font-family` of their headings and body, and their Google Fonts link (an `<link>` or `@import` to
   fonts.googleapis.com). Copy that link as is into `google_fonts_url`. A font that is not on Google Fonts (Adobe,
   self-hosted, system): pick the closest Google font and say so in one line. Only fonts.googleapis.com links load.
7. Logo: download their logo image (header `<img>`, png, svg or jpg) into `ST/brand/logo.png` (keep its real
   extension) and set `"logo": "brand/logo.png"`. It sits on `bg`, so check it shows up on that color; a white logo
   on a light page does not. Skip the logo if there is no clean one. The page then shows their initial.
8. `name`: what they go by on camera, from `ST/about.md`, else their brand name. `source`: the URL you used.

## No site at all
Ask in one message: "Two colors you love for your brand (or hex codes), and the vibe: bold, calm, playful or
luxury?" Then build the set yourself: bold = dark bg with their brightest color as accent, a condensed heading font
(Bebas Neue, Anton, Oswald); calm = light warm bg, a soft serif heading (Fraunces, Instrument Serif); playful =
light bg, a rounded heading (Fredoka, Outfit); luxury = near-black bg, a thin serif (Cormorant Garamond) with a
muted gold or cream accent. Body font: Inter unless the vibe needs something else. `source`: "asked".
If they skip it, leave `brand.json` out: the page uses a calm neutral default theme.

## Changes later
"Change my dashboard colors / font / logo": edit only that field in `ST/brand.json`, then run with
`--rebuild --open` (a new look needs the page opened again; new data alone never does). Never rewrite the rest. If they rebrand their site, fetch it again and redo steps 2 to 7.

## What the page never shows
Scripts, ideas cards, the taste file, STATUS lines or keys. It reads the research only. Every label is in plain
words ("3.2x your usual"), with no em dashes. When a section is empty, the page tells them what to say to you; if
they say it, do that job (usually a refresh) and run the script again.
