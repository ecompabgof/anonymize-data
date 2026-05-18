"""DOCX handler: anonymizes paragraphs and table cells."""
import os
import sys
from docx import Document

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from presidio_helper import anonymize_text


def anonymize(path, output=None, template=None):
    doc = Document(path)

    # Paragraphs: anonymize text, preserve formatting by editing runs
    for p in doc.paragraphs:
        if not p.text.strip():
            continue
        anon = anonymize_text(p.text)
        if anon != p.text:
            # Rewrite first run, clear others to keep structure simple
            if p.runs:
                p.runs[0].text = anon
                for run in p.runs[1:]:
                    run.text = ''

    # Tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    anon = anonymize_text(cell.text)
                    if anon != cell.text:
                        # cell.text setter overrides — simplest approach
                        for para in cell.paragraphs:
                            for run in para.runs:
                                run.text = ''
                        if cell.paragraphs and cell.paragraphs[0].runs:
                            cell.paragraphs[0].runs[0].text = anon
                        elif cell.paragraphs:
                            cell.paragraphs[0].add_run(anon)

    if output:
        doc.save(output)
        return output

    # Inline: dump text
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(' | '.join(c.text for c in row.cells))
    return '\n'.join(parts)
