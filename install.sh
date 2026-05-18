#!/usr/bin/env bash
# Plugin Claude Code: anonymize-data — install one-shot
# Usage: bash install.sh
set -e

PLUGIN_NAME="anonymize-data"
PLUGIN_DIR="$HOME/.claude/plugins/$PLUGIN_NAME"
REPO_URL="${ANONYMIZE_REPO:-https://github.com/ecompabgof/anonymize-data}"

echo ""
echo "  Claude Code Plugin: anonymize-data v2.0"
echo "  Anonymisation locale RGPD (PDF/Image/XLSX/CSV/DOCX/PPTX/TXT)"
echo ""

# 1. Detect OS
OS="unknown"
case "$(uname -s)" in
  Darwin) OS="mac" ;;
  Linux)  OS="linux" ;;
  *) echo "OS non supporté: $(uname -s)"; exit 1 ;;
esac
echo "  OS detecté: $OS"

# 2. Check prerequisites
need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "  Manque: $1"; return 1; }
}

echo ""
echo "  Vérification prérequis..."
MISSING=""
need_cmd python3 || MISSING="$MISSING python3"
need_cmd git || MISSING="$MISSING git"

if [ "$OS" = "mac" ]; then
  need_cmd brew || MISSING="$MISSING brew"
fi

if [ -n "$MISSING" ]; then
  echo ""
  echo "  Installe d'abord:$MISSING"
  echo "  Mac: https://brew.sh — install Homebrew puis 'brew install python git'"
  exit 1
fi

# 3. Install system deps
echo ""
echo "  Installation outils système (tesseract, ghostscript, poppler)..."
if [ "$OS" = "mac" ]; then
  brew install tesseract tesseract-lang ghostscript poppler 2>&1 | grep -v "already installed" | tail -5 || true
elif [ "$OS" = "linux" ]; then
  if command -v apt-get >/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y tesseract-ocr tesseract-ocr-fra ghostscript poppler-utils
  elif command -v dnf >/dev/null; then
    sudo dnf install -y tesseract tesseract-langpack-fra ghostscript poppler-utils
  fi
fi

# 4. Clone or update plugin
echo ""
echo "  Récupération plugin..."
if [ -d "$PLUGIN_DIR" ]; then
  echo "  Déjà présent: $PLUGIN_DIR (skip clone)"
else
  mkdir -p "$HOME/.claude/plugins"
  # Try git clone, fallback to local copy if running from existing dir
  if git clone "$REPO_URL" "$PLUGIN_DIR" 2>/dev/null; then
    echo "  Cloné depuis $REPO_URL"
  else
    echo "  Repo distant indisponible. Pour install local, place les fichiers dans $PLUGIN_DIR"
    exit 1
  fi
fi

# 5. Create venv + install python deps
echo ""
echo "  Création venv Python..."
python3 -m venv "$PLUGIN_DIR/.venv"
VENV_PY="$PLUGIN_DIR/.venv/bin/python"
VENV_PIP="$PLUGIN_DIR/.venv/bin/pip"

echo "  Installation dépendances Python (peut prendre 3-5min)..."
"$VENV_PIP" install --upgrade pip --quiet
"$VENV_PIP" install --quiet -r "$PLUGIN_DIR/requirements.txt"

# 6. spaCy models (bypass uv intercept via direct URL)
echo ""
echo "  Téléchargement modèles spaCy fr+en..."
"$VENV_PIP" install --quiet \
  https://github.com/explosion/spacy-models/releases/download/fr_core_news_md-3.8.0/fr_core_news_md-3.8.0-py3-none-any.whl \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# 7. Permissions
chmod +x "$PLUGIN_DIR/hooks/pre-prompt.sh"

# 8. Smoke test
echo ""
echo "  Test rapide..."
echo "Madame Jean DUPONT, 14 rue de la Paix, 75001 Paris. Tel: 06 12 34 56 78. NIR: 1 85 04 75 116 001 42" > /tmp/anonymize_smoke.txt
RESULT=$("$VENV_PY" "$PLUGIN_DIR/scripts/anonymize.py" /tmp/anonymize_smoke.txt 2>&1 || echo "FAIL")
rm -f /tmp/anonymize_smoke.txt

if echo "$RESULT" | grep -q "\[CIVILITE\]\|\[NOM\]"; then
  echo "  Test OK: $RESULT"
else
  echo "  Test KO. Résultat: $RESULT"
  echo "  Vérifie install et relance."
  exit 1
fi

# 9. Done
echo ""
echo "  ✓ Installation réussie"
echo ""
echo "  Usage dans Claude Code:"
echo "    @fiche_paye.pdf analyse ce salaire"
echo "    @journal.xlsx fais total"
echo "    @photo.jpg lis cette photo"
echo ""
echo "  IMPORTANT: redémarre Claude Code (Cmd+Q puis relance) pour charger le plugin."
echo ""
