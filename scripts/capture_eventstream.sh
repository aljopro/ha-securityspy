#!/usr/bin/env bash
#
# Capture the SecuritySpy event stream for an extended period.
#
# The stream is CR-framed and never ends by design, so this reconnects on drop
# and records where each connection began. That boundary matters: EVENT_NUMBER
# is a per-connection counter that restarts at 0, so a record is only uniquely
# identified by (connection, event number) -- never by event number alone.
#
# Credentials are passed to curl on stdin, never in argv, so they do not appear
# in `ps` output.
#
# Usage:
#   scripts/capture_eventstream.sh [OUTFILE]
#
#   DURATION=3600  scripts/capture_eventstream.sh out.log   # stop after an hour
#   DURATION=0     scripts/capture_eventstream.sh out.log   # until Ctrl-C (default)
#
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/../aiosecurityspy/.env}"
OUT="${1:-eventstream-$(date +%Y%m%d-%H%M%S).log}"
DURATION="${DURATION:-0}"          # total seconds; 0 = run until interrupted
CONNECT_MAX="${CONNECT_MAX:-3600}" # seconds per single connection

if [[ ! -f "$ENV_FILE" ]]; then
  echo "no env file at $ENV_FILE (copy aiosecurityspy/.env.example)" >&2
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

USER_NAME="${SECURITYSPY_ADMIN_USER:-}"
USER_PASS="${SECURITYSPY_ADMIN_PASS:-}"
if [[ -z "${SECURITYSPY_HOST:-}" || -z "$USER_NAME" ]]; then
  echo "SECURITYSPY_HOST and SECURITYSPY_ADMIN_USER must be set in $ENV_FILE" >&2
  exit 1
fi

SCHEME=https; [[ "${SECURITYSPY_USE_HTTPS:-1}" == "0" ]] && SCHEME=http
INSECURE=(); [[ "${SECURITYSPY_VERIFY_SSL:-0}" == "0" ]] && INSECURE=(-k)
URL="$SCHEME://$SECURITYSPY_HOST:${SECURITYSPY_PORT:-8001}/++eventStream?version=3"

: > "$OUT" || { echo "cannot write $OUT" >&2; exit 1; }

# Records are CR-terminated, so counting lines would not see them: count CRs.
record_count() { tr -cd '\r' < "$OUT" 2>/dev/null | wc -c | tr -d ' '; }

started=$(date +%s)
conn=0
running=1
trap 'running=0; echo; echo "stopping..." >&2' INT TERM

echo "capturing -> $OUT   (Ctrl-C to stop)" >&2
while (( running )); do
  if (( DURATION > 0 )); then
    elapsed=$(( $(date +%s) - started ))
    (( elapsed >= DURATION )) && break
    remaining=$(( DURATION - elapsed ))
    (( remaining < CONNECT_MAX )) && CONNECT_MAX=$remaining
  fi

  conn=$((conn + 1))
  before=$(record_count)
  printf '\n#CONNECT %d %s\n' "$conn" "$(date -Iseconds)" >> "$OUT"

  # Written RAW, straight from curl: no `tr`/`grep` in the path. Those block-buffer
  # when stdout is a file, so on a quiet camera the capture would sit invisibly in a
  # 4 KB buffer for many minutes and lose its tail if the process were killed hard.
  # The wire bytes are CR-framed; the analyzer splits on CR and LF alike.
  printf 'user = "%s:%s"\n' "$USER_NAME" "$USER_PASS" \
    | curl -s "${INSECURE[@]}" --no-buffer --max-time "$CONNECT_MAX" -K - "$URL" >> "$OUT" 2>/dev/null

  after=$(record_count)
  printf '\n#DISCONNECT %d %s records=%d\n' \
    "$conn" "$(date -Iseconds)" "$(( after - before ))" >> "$OUT"

  (( running )) || break
  (( DURATION > 0 )) && (( $(date +%s) - started >= DURATION )) && break
  sleep 2   # the stream ended; give the server a moment before reconnecting
done

echo "done: $conn connection(s), $(record_count) records -> $OUT" >&2
