#!/usr/bin/env bash
# anonymize-data : installe le moteur local (Python, spaCy, lecteurs de fichiers) dans ~/.anonymize-data/venv.
# Le plugin Claude Code s'installe à part : /plugin marketplace add ecompabgof/anonymize-data
#
#   bash install.sh          moteur seul
#   bash install.sh --ocr    moteur + Tesseract pour les PDF scannés et les photos (Homebrew ou apt)
set -euo pipefail

HOME_DIR="${ANONYMIZE_DATA_HOME:-$HOME/.anonymize-data}"
VENV="$HOME_DIR/venv"
RAW="https://raw.githubusercontent.com/ecompabgof/anonymize-data/main"
SRC="${BASH_SOURCE[0]:-}"
if [ -n "$SRC" ] && [ -f "$SRC" ]; then DIR="$(cd "$(dirname "$SRC")" && pwd)"; else DIR=""; fi  # empty when piped
MODEL="https://github.com/explosion/spacy-models/releases/download/fr_core_news_md-3.8.0/fr_core_news_md-3.8.0-py3-none-any.whl"
OCR=0
[ "${1:-}" = "--ocr" ] && OCR=1

say() { printf '  %s\n' "$*"; }

echo
say "anonymize-data : installation du moteur local"
echo

command -v python3 >/dev/null || { say "python3 manquant. Mac : installe-le avec 'brew install python'."; exit 1; }
python3 - <<'PY' || { say "Python 3.9 ou plus récent est nécessaire."; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)
PY

if [ "$OCR" = 1 ]; then
  say "Installation de Tesseract (OCR)..."
  if command -v brew >/dev/null; then
    brew install tesseract tesseract-lang
  elif command -v apt-get >/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y tesseract-ocr tesseract-ocr-fra
  else
    say "Ni Homebrew ni apt : installe Tesseract à la main, puis relance."
  fi
fi

mkdir -p "$HOME_DIR"
chmod 700 "$HOME_DIR"
if [ ! -x "$VENV/bin/python" ]; then
  say "Création de l'environnement Python dans $VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip

REQ="${DIR:+$DIR/requirements.txt}"
if [ -z "$REQ" ] || [ ! -f "$REQ" ]; then
  REQ="$HOME_DIR/requirements.txt"
  curl -fsSL "$RAW/requirements.txt" -o "$REQ"
fi
say "Installation des bibliothèques (quelques minutes la première fois)..."
"$VENV/bin/python" -m pip install --quiet -r "$REQ"
"$VENV/bin/python" -m pip install --quiet "$MODEL"
"$VENV/bin/python" -m pip install --quiet "pillow-heif>=0.16" 2>/dev/null || say "Photos HEIC non prises en charge sur ce poste (facultatif)."

say "Vérification sur un exemple fictif..."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf 'Salarié : DUPONT Jean, IBAN FR76 3000 6000 0112 3456 7890 189.\n' > "$TMP/essai.txt"
if [ -n "$DIR" ] && [ -f "$DIR/anonymizer/cli.py" ]; then
  CLI="$DIR/anonymizer/cli.py"
else
  CLI=""
fi
if [ -n "$CLI" ]; then
  ANONYMIZE_DATA_HOME="$TMP/reg" "$VENV/bin/python" "$CLI" "$TMP/essai.txt" --sortie "$TMP/out" >/dev/null || true
  OUT="$(cat "$TMP"/out/*.md 2>/dev/null || true)"
  if printf '%s' "$OUT" | grep -q '\[PERSONNE_1\]' && ! printf '%s' "$OUT" | grep -q 'DUPONT\|FR76'; then
    say "Test OK."
  else
    say "Test KO : le moteur n'a pas masqué l'exemple. Ne t'en sers pas avant d'avoir corrigé."
    exit 1
  fi
else
  "$VENV/bin/python" -c "import spacy; spacy.load('fr_core_news_md')" && say "Bibliothèques OK."
fi

if ! command -v tesseract >/dev/null; then
  say "OCR absent : les PDF scannés et les photos seront refusés. Pour l'ajouter : bash install.sh --ocr"
fi
echo
say "Moteur installé. Dans Claude Code :"
say "  /plugin marketplace add ecompabgof/anonymize-data"
say "  /plugin install anonymize-data@anonymize-data"
say "Active le plugin seulement dans les dossiers qui contiennent des documents clients."
echo
