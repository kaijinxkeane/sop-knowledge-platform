#!/bin/bash
# Validate plugin manifest and command/skill frontmatter
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PLUGIN_DIR="$PROJECT_ROOT/claude-plugin"
PLUGIN_JSON="$PLUGIN_DIR/.claude-plugin/plugin.json"
PASS=0
FAIL=0
TOTAL=0
REFERENCE_NAMES="archive audit command-prelude compilation feedback hub-resolution indexing ingestion inventory librarian linting projects query-lite refresh research-infrastructure sessions wiki-structure"

log_pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); printf "  \033[32mPASS\033[0m: %s\n" "$1"; }
log_fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); printf "  \033[31mFAIL\033[0m: %s — %s\n" "$1" "$2"; }

echo "=== Plugin Validation ==="

# plugin.json
if [ -f "$PLUGIN_JSON" ]; then
  log_pass "plugin.json exists"
  if python3 -c "import json; json.load(open('$PLUGIN_JSON'))" 2>/dev/null; then
    log_pass "plugin.json is valid JSON"
  else
    log_fail "plugin.json is invalid JSON" "parse error"
  fi
else
  log_fail "plugin.json not found at $PLUGIN_JSON" "missing file"
fi

# Every command .md has frontmatter (starts with ---)
echo ""
echo "--- Command frontmatter ---"
for cmd in "$PLUGIN_DIR"/commands/*.md; do
  basename=$(basename "$cmd")
  if head -1 "$cmd" | grep -q "^---$"; then
    log_pass "frontmatter in commands/$basename"
  else
    log_fail "no frontmatter in commands/$basename" "missing ---"
  fi
done

# The lessons-learned command writes a raw note, so its embedded template must
# use the same frontmatter schema that lint accepts for raw/notes/*.md.
LL_COMMAND="$PLUGIN_DIR/commands/ll.md"
if grep -q '^type: notes$' "$LL_COMMAND" \
  && grep -q '^ingested: YYYY-MM-DD$' "$LL_COMMAND" \
  && grep -q '^lesson_kind: lessons-learned$' "$LL_COMMAND" \
  && ! grep -q '^type: lessons-learned$' "$LL_COMMAND" \
  && ! grep -q '^date: YYYY-MM-DD$' "$LL_COMMAND"; then
  log_pass "commands/ll.md raw-note template matches lint schema"
else
  log_fail "commands/ll.md raw-note template schema drift" "expected type: notes, ingested, and lesson_kind"
fi

# Topic guides must influence every runtime through the shared compilation
# protocol without becoming a second schema or hiding raw-source coverage.
COMPILE_COMMAND="$PLUGIN_DIR/commands/compile.md"
COMPILATION_REFERENCE="$PLUGIN_DIR/skills/wiki-manager/references/compilation.md"
WIKI_STRUCTURE_REFERENCE="$PLUGIN_DIR/skills/wiki-manager/references/wiki-structure.md"
if grep -q 'references/compilation.md.*Topic-guide preflight' "$COMPILE_COMMAND" \
  && grep -q '^### Step 0: Topic-guide preflight$' "$COMPILATION_REFERENCE" \
  && grep -q 'cannot mark' "$COMPILATION_REFERENCE" \
  && grep -q 'For `schema_state: strict`, stop' "$COMPILATION_REFERENCE" \
  && grep -q 'Every runtime.*compilation workflow reads' "$WIKI_STRUCTURE_REFERENCE" \
  && grep -q 'does not satisfy C6' "$WIKI_STRUCTURE_REFERENCE"; then
  log_pass "topic-guide compilation is runtime-neutral and preserves coverage"
else
  log_fail "topic-guide compilation contract drift" "expected shared planning guidance, strict confirmation, and C6 coverage"
fi

# SKILL.md exists
echo ""
echo "--- Skill files ---"
if [ -f "$PLUGIN_DIR/skills/wiki-manager/SKILL.md" ]; then
  log_pass "SKILL.md exists"
  if head -1 "$PLUGIN_DIR/skills/wiki-manager/SKILL.md" | grep -q "^---$"; then
    log_pass "SKILL.md has frontmatter"
  else
    log_fail "SKILL.md has no frontmatter" "missing ---"
  fi
else
  log_fail "SKILL.md not found" "missing file"
fi

# Reference files exist
echo ""
echo "--- Reference files ---"
for ref in $REFERENCE_NAMES; do
  reffile="$PLUGIN_DIR/skills/wiki-manager/references/${ref}.md"
  if [ -f "$reffile" ]; then
    log_pass "references/$ref.md exists"
  else
    log_fail "references/$ref.md missing" "missing file"
  fi
done

CLAUDE_LOCAL_CLI="$PLUGIN_DIR/bin/llm-wiki"
if [ -x "$CLAUDE_LOCAL_CLI" ] \
  && cmp -s "$CLAUDE_LOCAL_CLI" "$PROJECT_ROOT/scripts/llm-wiki"; then
  log_pass "Claude plugin bundles the current deterministic llm-wiki CLI"
else
  log_fail "Claude bundled llm-wiki CLI missing or stale" "run a plugin sync script"
fi


echo ""
echo "==========================================="
printf "Results: \033[32m%d passed\033[0m, \033[31m%d failed\033[0m, %d total\n" "$PASS" "$FAIL" "$TOTAL"
echo "==========================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
