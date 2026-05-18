#!/usr/bin/env python3
"""Router: detects file ext and dispatches to right handler."""
import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handlers import pdf, image, xlsx, csv as csvh, docx as docxh, pptx as pptxh, text

ROUTERS = {
    '.pdf': pdf.anonymize,
    '.png': image.anonymize,
    '.jpg': image.anonymize,
    '.jpeg': image.anonymize,
    '.webp': image.anonymize,
    '.bmp': image.anonymize,
    '.tiff': image.anonymize,
    '.tif': image.anonymize,
    '.gif': image.anonymize,
    '.heic': image.anonymize,
    '.avif': image.anonymize,
    '.xlsx': xlsx.anonymize,
    '.xls': xlsx.anonymize,
    '.csv': csvh.anonymize,
    '.tsv': csvh.anonymize,
    '.docx': docxh.anonymize,
    '.pptx': pptxh.anonymize,
    '.txt': text.anonymize,
    '.md': text.anonymize,
}


def main():
    parser = argparse.ArgumentParser(description='Anonymise local files before sending to Claude.')
    parser.add_argument('file', help='File path to anonymize')
    parser.add_argument('--output', default=None, help='Output file path (write mode)')
    parser.add_argument('--template', default=None, help='Template name (in templates/)')
    args = parser.parse_args()

    ext = Path(args.file).suffix.lower()
    if ext not in ROUTERS:
        print(f'Type non supporté: {ext}. Types acceptés: {sorted(ROUTERS.keys())}',
              file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.file):
        print(f'Fichier introuvable: {args.file}', file=sys.stderr)
        sys.exit(1)

    try:
        result = ROUTERS[ext](args.file, output=args.output, template=args.template)
        print(result)
    except Exception as e:
        print(f'Erreur anonymisation {args.file}: {e}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
