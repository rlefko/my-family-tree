#!/usr/bin/env bash
# Enforce: commit subject is one sentence with no ending punctuation, prefixed
# by an emoji. Comment lines (lines starting with '#') are ignored.
set -euo pipefail

msg_file="$1"
subject="$(grep -v '^#' "$msg_file" | head -n 1)"

if [[ -z "$subject" ]]; then
  echo "commit-msg: empty subject" >&2
  exit 1
fi

# Reject trailing punctuation.
case "$subject" in
  *.|*!|*?|*,|*\;|*\:)
    echo "commit-msg: subject must not end with punctuation: '$subject'" >&2
    exit 1
    ;;
esac

# Match a leading emoji code point (0x1F300+ is the bulk of emoji).
python3 - "$subject" <<'PY'
import sys, unicodedata
subject = sys.argv[1]
if not subject:
    print("commit-msg: empty subject", file=sys.stderr); sys.exit(1)
first = subject[0]
cp = ord(first)
emoji_ranges = [
    (0x1F300, 0x1F6FF), (0x1F700, 0x1F77F), (0x1F780, 0x1F7FF),
    (0x1F800, 0x1F8FF), (0x1F900, 0x1F9FF), (0x1FA00, 0x1FA6F),
    (0x1FA70, 0x1FAFF), (0x2600, 0x26FF), (0x2700, 0x27BF),
]
if not any(lo <= cp <= hi for lo, hi in emoji_ranges):
    print(f"commit-msg: subject must start with an emoji, got '{first}' (U+{cp:04X})", file=sys.stderr)
    sys.exit(1)
PY
