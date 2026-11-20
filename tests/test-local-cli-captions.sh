#!/bin/bash
# Validate the local deterministic llm-wiki captions helper (VTT/SRT -> text).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLI="$PROJECT_ROOT/scripts/llm-wiki"
PASS=0
FAIL=0
TOTAL=0

log_pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); printf "  \033[32mPASS\033[0m: %s\n" "$1"; }
log_fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); printf "  \033[31mFAIL\033[0m: %s - %s\n" "$1" "$2"; }

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

# YouTube-style rolling auto-captions: each cue repeats the previous line,
# carries <c> word-timing tags, and has 10ms "hold" cues.
cat > "$tmpdir/auto.en.vtt" <<'EOF'
WEBVTT
Kind: captions
Language: en

00:00:00.160 --> 00:00:02.869 align:start position:0%
@SP@
hello<00:00:00.640><c> and</c><00:00:00.800><c> welcome</c>

00:00:02.869 --> 00:00:02.879 align:start position:0%
hello and welcome
@SP@

00:00:02.879 --> 00:00:05.430 align:start position:0%
hello and welcome
to<00:00:03.120><c> the</c><00:00:03.300><c> show</c>

00:00:05.430 --> 00:00:05.440 align:start position:0%
to the show
@SP@

00:01:05.440 --> 00:01:08.000 align:start position:0%
to the show
today&amp;tomorrow<c> we</c><c> talk</c>

01:02:03.000 --> 01:02:04.000
hello and welcome
EOF
sed -i.bak 's/^@SP@$/ /' "$tmpdir/auto.en.vtt" && rm -f "$tmpdir/auto.en.vtt.bak"

cat > "$tmpdir/manual.srt" <<'EOF'
1
00:00:01,000 --> 00:00:03,000
<i>First line.</i>

2
00:00:03,500 --> 00:00:05,000
Second line,
continued.
EOF

printf 'WEBVTT\n\nNOTE nothing here\n' > "$tmpdir/empty.vtt"

echo "Captions helper"

out="$("$CLI" captions "$tmpdir/auto.en.vtt")"
expected='[00:00] hello and welcome to the show

[01:05] today&tomorrow we talk

[1:02:03] hello and welcome'
if [ "$out" = "$expected" ]; then
  log_pass "VTT rolling captions de-duplicated into timestamped paragraphs"
else
  log_fail "VTT rolling captions" "got: $out"
fi

if printf '%s' "$out" | grep -q '<c>\|-->\|WEBVTT\|align:'; then
  log_fail "VTT markup stripped" "timing or tags leaked"
else
  log_pass "VTT timing, settings, and <c> tags stripped"
fi

out="$("$CLI" captions --no-timestamps --paragraph-seconds 0 "$tmpdir/auto.en.vtt")"
if [ "$out" = "hello and welcome to the show today&tomorrow we talk hello and welcome" ]; then
  log_pass "--no-timestamps --paragraph-seconds 0 gives one plain paragraph (later repeats kept)"
else
  log_fail "plain paragraph" "got: $out"
fi

out="$("$CLI" captions --no-timestamps "$tmpdir/manual.srt")"
if [ "$out" = "First line. Second line, continued." ]; then
  log_pass "SRT sequence numbers and <i> tags removed"
else
  log_fail "SRT parsing" "got: $out"
fi

json="$("$CLI" captions --json "$tmpdir/auto.en.vtt")"
if printf '%s' "$json" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["line_count"]==4 and d["duration_seconds"]==3723 and len(d["paragraphs"])==3, d'; then
  log_pass "--json reports line_count, duration_seconds, paragraphs"
else
  log_fail "--json" "unexpected report: $json"
fi

set +e
"$CLI" captions "$tmpdir/empty.vtt" >/dev/null 2>"$tmpdir/err"; rc=$?
set -e
if [ "$rc" -eq 1 ] && grep -q 'no caption cues' "$tmpdir/err"; then
  log_pass "file with no cues exits 1 with a clear message"
else
  log_fail "empty captions" "rc=$rc err=$(cat "$tmpdir/err")"
fi

set +e
"$CLI" captions "$tmpdir/missing.vtt" >/dev/null 2>&1; rc=$?
set -e
if [ "$rc" -eq 2 ]; then
  log_pass "missing file exits 2"
else
  log_fail "missing file" "rc=$rc"
fi

echo ""
echo "Results: $PASS/$TOTAL passed"
[ "$FAIL" -eq 0 ]
