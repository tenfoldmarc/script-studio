# Script Studio

Claude studies what already works on your account, your competitors' accounts and the places your audience hangs out. Then it writes ready-to-record reel scripts in your voice.

Script Studio is an add-on for Claude Creator Studio. Install the Studio first. Your walkthrough and support are in your portal: https://portal.tenfoldmarketing.com

## Install in the Claude desktop app

1. Open the Claude desktop app and go to the **Code** tab.
2. Click the **+** next to the message box, then **Plugins**, then **Browse plugins**.
3. Click **Add** in the top right, then **Add marketplace**, then **Add from a repository**.
4. Paste the Script Studio link from your portal and click **Sync**.
5. Install **Script Studio** from the list.
6. Start a new chat and type:

```
/script-studio
```

Setup takes about two minutes of your time. You give it your handle, 3 to 10 accounts whose reels pop in your space, and where your audience hangs out (subreddits, X accounts, newsletters). It asks you to copy a free Apify key. Then it studies everything for about 10 to 15 minutes while you answer four quick questions.

## Every day after that

```
give me tomorrow's reel
```

You get 5 ideas, each backed by proof (a reel that crushed its creator's average, or a thread your audience is talking about). Pick one, and you get the script: the spoken lines, on-screen text, caption and 10 hook options, all in your voice. Film it, drop the clips in, and say "edit it". Claude Creator Studio edits the reel.

You can also say:

- `write me a script about [topic]`
- `make my version of this reel [link]`
- `give me a week of scripts`
- `what's working on my account`
- `refresh my research`

## Install from a terminal instead

Only if you use Claude Code in Terminal (Mac) or PowerShell (Windows). Run these yourself, not inside Claude.

```bash
claude plugin marketplace add <the Script Studio link from your portal>
```

```bash
claude plugin install script-studio@script-studio
```
