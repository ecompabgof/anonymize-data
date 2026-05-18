"""PDF handler: OCR via ocrmypdf (Tesseract) + Presidio anonymization."""
import os
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from presidio_helper import anonymize_text


def _find_ocrmypdf():
    """Resolve ocrmypdf binary: prefer plugin venv, then PATH."""
    venv_bin = os.path.expanduser('~/.claude/plugins/anonymize-data/.venv/bin/ocrmypdf')
    if os.path.exists(venv_bin):
        return venv_bin
    return 'ocrmypdf'


def _ocr_pdf_to_text(pdf_path):
    """Run ocrmypdf with sidecar text output. Returns extracted text."""
    OCRMYPDF = _find_ocrmypdf()
    with tempfile.TemporaryDirectory() as tmp:
        sidecar = os.path.join(tmp, 'out.txt')
        out_pdf = os.path.join(tmp, 'ocr.pdf')
        cmd = [
            OCRMYPDF, '--force-ocr', '-l', 'fra+eng',
            '--sidecar', sidecar, pdf_path, out_pdf
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Try without --force-ocr (if pdf already has text layer)
            cmd_fallback = [
                OCRMYPDF, '--skip-text', '-l', 'fra+eng',
                '--sidecar', sidecar, pdf_path, out_pdf
            ]
            result = subprocess.run(cmd_fallback, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f'ocrmypdf failed: {result.stderr}')
        if not os.path.exists(sidecar):
            return ''
        return Path(sidecar).read_text(encoding='utf-8', errors='replace')


def anonymize(path, output=None, template=None):
    text = _ocr_pdf_to_text(path)
    anon = anonymize_text(text)
    if output:
        out_path = output if output.endswith(('.txt', '.md')) else output + '.txt'
        Path(out_path).write_text(anon, encoding='utf-8')
        return out_path
    return anon
