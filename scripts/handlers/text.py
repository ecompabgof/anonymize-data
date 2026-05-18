"""Plain text / markdown handler."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from presidio_helper import anonymize_text


def anonymize(path, output=None, template=None):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    anon = anonymize_text(text)
    if output:
        Path(output).write_text(anon, encoding='utf-8')
        return output
    return anon
