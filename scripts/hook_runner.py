#!/usr/bin/env python3
"""Cross-platform hook runner.

Reads UserPromptSubmit JSON on stdin, detects @path.ext mentions,
runs the anonymizer locally, replaces with anonymized text, prints
modified JSON to stdout.

Works on Mac, Linux, and Windows (no bash dependency).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent
ANON_SCRIPT = PLUGIN_DIR / "scripts" / "anonymize.py"

# Pick venv Python (cross-platform)
if os.name == "nt":
    VENV_PY = PLUGIN_DIR / ".venv" / "Scripts" / "python.exe"
else:
    VENV_PY = PLUGIN_DIR / ".venv" / "bin" / "python"

PY = str(VENV_PY) if VENV_PY.exists() else sys.executable

EXTS = (
    "pdf", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif", "gif",
    "heic", "avif", "xlsx", "xls", "csv", "tsv", "docx", "pptx", "txt", "md",
)

# Match: @path.ext  optionally followed by --output=... or --template=...
PATTERN = re.compile(
    r"@(?P<path>[^\s]+?\.(?:" + "|".join(EXTS) + r"))"
    r"(?P<flags>(?:\s+--[a-z]+=\S+)*)",
    re.IGNORECASE,
)


def expanduser(p: str) -> str:
    """Resolve ~, $HOME, %USERPROFILE% in path."""
    p = os.path.expandvars(p)
    p = os.path.expanduser(p)
    return p


def anonymize_file(path: str, output: str | None, template: str | None) -> str:
    cmd = [PY, str(ANON_SCRIPT), path]
    if output:
        cmd.append(f"--output={output}")
    if template:
        cmd.append(f"--template={template}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            return result.stdout.rstrip()
        return f"[ERREUR anonymisation: {result.stderr.strip()[:200]}]"
    except subprocess.TimeoutExpired:
        return "[ERREUR: anonymisation timeout 180s]"
    except Exception as e:
        return f"[ERREUR: {e}]"


def parse_flags(flag_str: str) -> dict:
    flags = {}
    for m in re.finditer(r"--(\w+)=(\S+)", flag_str):
        flags[m.group(1)] = m.group(2)
    return flags


def process_prompt(prompt: str) -> str:
    matches = list(PATTERN.finditer(prompt))
    if not matches:
        return prompt

    # Process in reverse to preserve indices when replacing
    modified = prompt
    for m in reversed(matches[:20]):  # safety cap
        raw_path = m.group("path")
        path = expanduser(raw_path)

        if not os.path.isfile(path):
            continue

        flags = parse_flags(m.group("flags") or "")
        output = flags.get("output")
        template = flags.get("template")

        if output:
            output = expanduser(output)

        result = anonymize_file(path, output, template)
        basename = os.path.basename(path)

        if output:
            replacement = f"[Fichier anonymisé écrit dans: {result}]"
        else:
            replacement = f"[ANONYMISÉ — {basename}]\n{result}\n[FIN ANONYMISÉ]"

        modified = modified[: m.start()] + replacement + modified[m.end():]

    return modified


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Not JSON — passthrough
        sys.stdout.write(raw)
        return

    prompt = data.get("prompt", "")
    if prompt:
        data["prompt"] = process_prompt(prompt)

    sys.stdout.write(json.dumps(data))


if __name__ == "__main__":
    main()
