#!/bin/sh
# Script Studio quiet check (Mac and Linux). Script Studio runs on Creator Studio's own Python
# (it already has the transcription engine and ffmpeg). This finds it, sets it up through the Studio when it is
# missing, then prints the STATUS lines. Never runs a bare python3 (on a Mac that can open an Xcode prompt).
SS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
case "$(uname -s)" in
  Darwin) STUDIO_STATE="$HOME/Library/Application Support/video-studio" ;;
  *) STUDIO_STATE="${XDG_DATA_HOME:-$HOME/.local/share}/video-studio" ;;
esac

find_py() {
  PLAT="$STUDIO_STATE/.platform.json"
  [ -f "$PLAT" ] || return 1
  PY="$(sed -n 's/^ *"python": *"\(.*\)",*$/\1/p' "$PLAT" | head -n 1)"
  [ -n "$PY" ] && [ -x "$PY" ]
}

if ! find_py; then
  # the Studio was never set up on this computer: run its own setup (it gets Python, ffmpeg, Whisper)
  STUDIO_START="$(ls -d "$HOME"/.claude/plugins/cache/*/video-studio/*/skills/video-studio/scripts/start.sh 2>/dev/null | sort -V | tail -n 1)"
  if [ -z "$STUDIO_START" ]; then
    echo "STATUS studio NOT_INSTALLED"
    exit 0
  fi
  echo "SETUP running the Creator Studio setup first (one time, a few minutes)"
  sh "$STUDIO_START" >/dev/null 2>&1
  if ! find_py; then
    echo "STATUS studio SETUP_FAILED"
    exit 0
  fi
fi
echo "PY $PY"
exec "$PY" "$SS_DIR/scripts/ss.py" check
