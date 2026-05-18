"""CSV/TSV handler: drops sensitive columns + anonymizes free text."""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from presidio_helper import anonymize_text
from handlers.xlsx import SENSITIVE_KEYWORDS


def anonymize(path, output=None, template=None):
    sep = '\t' if path.endswith('.tsv') else ','
    df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False)

    # Detect sensitive columns by header keyword match
    sensitive_cols = [
        c for c in df.columns
        if any(kw in c.lower() for kw in SENSITIVE_KEYWORDS)
    ]
    if sensitive_cols:
        df = df.drop(columns=sensitive_cols)

    # Anonymize long-text cells in remaining cols
    for col in df.columns:
        df[col] = df[col].apply(
            lambda x: anonymize_text(x) if isinstance(x, str) and len(x) > 10 else x
        )

    if output:
        df.to_csv(output, sep=sep, index=False)
        return output
    return df.to_csv(sep=sep, index=False)
