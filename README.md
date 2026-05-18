# anonymize-data

Plugin Claude Code: anonymisation locale RGPD avant que Claude voie tes données.

Détecte `@fichier.pdf` (et autres) dans le prompt, lance OCR + NER local, remplace par texte anonymisé. **Claude ne reçoit jamais les données brutes.**

## Formats supportés

PDF, JPG/PNG/WEBP/AVIF/HEIC/TIFF/BMP/GIF, XLSX/XLS, CSV/TSV, DOCX, PPTX, TXT/MD

## Entités détectées

NOM, EMAIL, TÉLÉPHONE (FR), IBAN, ADRESSE (FR), CP+VILLE (FR), NIR (sécu FR), SIRET, SIREN, TVA intra UE, CB, DATE, URL, IP, MATRICULE, CIVILITÉ.

## Install (1 commande)

```bash
curl -sSL https://raw.githubusercontent.com/ecompabgof/anonymize-data/main/install.sh | bash
```

Prérequis: `python3`, `git`, Homebrew (Mac) ou `apt`/`dnf` (Linux).

L'installeur fait:
- Tesseract + ghostscript + poppler via brew/apt
- Venv Python + Presidio + ocrmypdf + spaCy fr+en
- Smoke test

Puis **redémarre Claude Code** (Cmd+Q) pour charger le plugin.

## Usage

```
@fiche_paye.pdf analyse ce salaire
@journal.xlsx fais total
@photo.jpg lis cette photo
@contrat.docx résume

# Mode output: écrit fichier anonymisé propre
@journal.xlsx --output=clean.xlsx

# Template (structure connue)
@bulletin.pdf --template=fiche_paye
@journal.xlsx --template=journal_paye
```

## Architecture

```
~/.claude/plugins/anonymize-data/
├── plugin.json
├── hooks/pre-prompt.sh          # intercept @path.ext
├── scripts/
│   ├── anonymize.py              # router
│   ├── presidio_helper.py        # NER fr+en + custom FR recognizers
│   └── handlers/                 # 1 fichier par format
└── templates/                    # YAML config par-structure (optionnel)
```

## Garanties RGPD

- ✅ 100% local (Tesseract OCR + Presidio + spaCy)
- ✅ Aucun appel API externe
- ✅ Claude reçoit uniquement texte anonymisé
- ✅ Fonctionne offline

## Tests

```bash
# Smoke test
echo "Madame Jean DUPONT, 14 rue de la Paix, 75001 Paris" > /tmp/t.txt
.venv/bin/python scripts/anonymize.py /tmp/t.txt
# → [CIVILITE], [ADRESSE], [CP_VILLE]
```

## License

MIT
