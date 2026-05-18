#!/bin/bash
# pre-prompt hook: detects @path.ext in user prompt and replaces with anonymized content
set -e

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

if [ -z "$PROMPT" ]; then
  echo "$INPUT"
  exit 0
fi

PLUGIN_DIR="$HOME/.claude/plugins/anonymize-data"
# Prefer plugin venv if present, fallback to system python3
if [ -x "$PLUGIN_DIR/.venv/bin/python" ]; then
  PY="$PLUGIN_DIR/.venv/bin/python"
else
  PY="${ANONYMIZE_PYTHON:-python3}"
fi

EXTS="pdf|png|jpg|jpeg|webp|bmp|tiff|tif|gif|heic|avif|xlsx|xls|csv|tsv|docx|pptx|txt|md"

MODIFIED="$PROMPT"

# Match: @/path/to/file.ext  optionally followed by --output=... or --template=...
# Limit 20 matches per prompt for safety
MATCHES=$(echo "$PROMPT" | grep -oE "@[^[:space:]]+\.($EXTS)([[:space:]]+--[a-z]+=[^[:space:]]+)*" | head -20 || true)

while IFS= read -r MATCH; do
  [ -z "$MATCH" ] && continue

  # Extract path (first token after @, before any --flag)
  PATH_CLEAN=$(echo "$MATCH" | sed -E 's/^@//' | awk '{print $1}')

  # Resolve ~ and relative paths
  PATH_CLEAN="${PATH_CLEAN/#\~/$HOME}"

  if [ ! -f "$PATH_CLEAN" ]; then
    continue
  fi

  # Extract flags
  OUTPUT_FLAG=""
  TEMPLATE_FLAG=""
  if [[ "$MATCH" == *"--output="* ]]; then
    OUT_VAL=$(echo "$MATCH" | grep -oE -- '--output=[^[:space:]]+' | head -1 | cut -d= -f2-)
    OUTPUT_FLAG="--output=$OUT_VAL"
  fi
  if [[ "$MATCH" == *"--template="* ]]; then
    TPL_VAL=$(echo "$MATCH" | grep -oE -- '--template=[^[:space:]]+' | head -1 | cut -d= -f2-)
    TEMPLATE_FLAG="--template=$TPL_VAL"
  fi

  # Run anonymizer
  RESULT=$("$PY" "$PLUGIN_DIR/scripts/anonymize.py" "$PATH_CLEAN" $OUTPUT_FLAG $TEMPLATE_FLAG 2>/dev/null || echo "ERREUR_ANONYMISATION")

  if [ -n "$OUTPUT_FLAG" ]; then
    REPLACEMENT="[Fichier anonymisé écrit dans: $RESULT]"
  else
    BASENAME=$(basename "$PATH_CLEAN")
    REPLACEMENT="[ANONYMISÉ — $BASENAME]
$RESULT
[FIN ANONYMISÉ]"
  fi

  # Escape MATCH for sed-safe replace via bash substitution
  MODIFIED="${MODIFIED//"$MATCH"/$REPLACEMENT}"
done <<< "$MATCHES"

# Output modified prompt as JSON
echo "$INPUT" | jq --arg p "$MODIFIED" '.prompt = $p'
