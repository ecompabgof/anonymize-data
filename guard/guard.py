#!/usr/bin/env python3
"""Claude Code guard for anonymize-data (standard library only).

    guard.py prompt   UserPromptSubmit: a message that @-mentions an original client file is blocked
                      before it is sent; a pseudonymised copy is made and the message to resend is given.
    guard.py tool     PreToolUse: Read, Edit, Grep and Bash may not open original client files.

An original is a file with a document extension (pdf, images, Office, csv...) whose fingerprint is not
in the registry of copies written by `anonymiser`. Any internal error blocks (fail closed).
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDED = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif", ".avif",
    ".xlsx", ".xlsm", ".xls", ".ods", ".csv", ".tsv", ".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp",
    ".eml", ".msg",
}
TEXT_GUARDED = {".csv", ".tsv", ".eml", ".rtf"}  # what ripgrep would read as text
RE_GUARDED_REF = re.compile(r"[^\s'\"`=<>|;&()]+\.(?:" + "|".join(e[1:] for e in sorted(GUARDED)) + r")\b",
                            re.IGNORECASE)
SAFE_PROGRAMS = {
    "ls", "open", "stat", "file", "du", "wc", "shasum", "sha256sum", "sha1sum", "md5", "md5sum", "mkdir", "rm",
    "rmdir", "touch", "chmod", "chown", "echo", "printf", "test", "[", "find", "mdfind", "cd", "pwd", "true",
    "false", "basename", "dirname", "realpath", "readlink", "anonymiser", "trash",
}
WRAPPERS = {"sudo", "env", "command", "nohup", "time", "exec", "nice", "caffeinate"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", "\n", "{", "}"}


def home() -> Path:
    return Path(os.environ.get("ANONYMIZE_DATA_HOME", Path.home() / ".anonymize-data"))


def engine_python() -> str | None:
    p = os.environ.get("ANONYMIZE_DATA_PYTHON") or str(home() / "venv" / "bin" / "python")
    return p if os.path.isfile(p) and os.access(p, os.X_OK) else None


_PRODUCED = None


def produced() -> set[str]:
    global _PRODUCED
    if _PRODUCED is None:
        try:
            _PRODUCED = set((home() / "produits.txt").read_text(encoding="utf-8").split())
        except OSError:
            _PRODUCED = set()
    return _PRODUCED


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_raw(path: Path) -> bool:
    """An original client document: guarded extension, exists, and not a copy written by anonymiser."""
    try:
        if path.suffix.lower() not in GUARDED or not path.is_file():
            return False
        return sha256(path) not in produced()
    except OSError:
        return True  # cannot check: treat as original


def resolve(p: str, cwd: str) -> Path:
    q = Path(os.path.expandvars(os.path.expanduser(p)))
    return q if q.is_absolute() else Path(cwd) / q


def in_home(p: Path) -> bool:
    try:
        return home().resolve() in (p.resolve(), *p.resolve().parents)
    except OSError:
        return False


# ---------------------------------------------------------------- prompt

RE_MENTION = re.compile(r"(?<![\w/@])@(?:\"([^\"]+)\"|'([^']+)'|(\S+))")


def mentions(prompt: str):
    for m in RE_MENTION.finditer(prompt):
        raw = m.group(1) or m.group(2) or m.group(3)
        if m.group(3):
            raw = re.sub(r"#L\d+(?:-\d+)?$", "", raw)
            raw = raw.rstrip(".,;:!?)]}>")
        yield m.start(), m.end(), raw


def on_prompt(data: dict) -> dict | None:
    prompt = data.get("prompt") or ""
    if "@" not in prompt:
        return None
    cwd = data.get("cwd") or os.getcwd()
    found = []
    for s, e, ref in mentions(prompt):
        p = resolve(ref, cwd)
        if is_raw(p):
            found.append((s, e, ref, p))
    if not found:
        return None
    lines = [f"anonymize-data : message non envoyé. Il citait {len(found)} fichier(s) client original(aux), "
             "qui serai(en)t parti(s) en clair."]
    py = engine_python()
    outputs = {}
    if py is None:
        lines.append("Le moteur d'anonymisation n'est pas installé. Lance dans un terminal : "
                     f"bash \"{ROOT / 'install.sh'}\"")
    else:
        out_dir = Path(cwd) / "anonymise"
        cmd = [py, str(ROOT / "anonymizer" / "cli.py"), "--json", "--sortie", str(out_dir)]
        cmd += [str(p) for *_, p in found]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=840, cwd=cwd)
            res = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except (subprocess.TimeoutExpired, ValueError, IndexError, OSError) as e:
            res = {"erreurs": [{"source": "", "message": f"anonymisation interrompue ({type(e).__name__})"}]}
        for p in res.get("produits", []):
            outputs[str(Path(p["source"]))] = Path(p["sortie"])
        if outputs:
            lines.append("")
            lines.append("Copie(s) pseudonymisée(s) créée(s) en local :")
            for src, out in outputs.items():
                lines.append(f"  {_rel(out, cwd)}")
        for a in res.get("avertissements", []):
            lines.append(f"Attention, {Path(a['source']).name} : {a['message']}")
        for err in res.get("erreurs", []):
            name = Path(err["source"]).name if err.get("source") else ""
            lines.append(f"Échec{(' pour ' + name) if name else ''} : {err['message']}")
    if outputs:
        new = prompt
        for s, e, ref, p in sorted(found, reverse=True):
            out = outputs.get(str(p))
            if out is not None:
                rel = _rel(out, cwd)
                new = new[:s] + ("@" + (f'"{rel}"' if " " in rel else rel)) + new[e:]
        lines.append("")
        lines.append("Relis la copie, puis renvoie ton message avec la copie à la place de l'original :")
        lines.append("")
        lines.append(new)
    return {"decision": "block", "reason": "\n".join(lines),
            "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}}


def _rel(p: Path, cwd: str) -> str:
    try:
        return os.path.relpath(p, cwd)
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- tools

def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": "anonymize-data : " + reason}}


ANONYMISER = Path(__file__).resolve().parent.parent / "bin" / "anonymiser"  # bin/ is not always on PATH
HOW = (f"Ne lis pas l'original. Lance seulement `{shlex.quote(str(ANONYMISER))} <chemin>` (seule commande, "
       "rien d'autre sur la ligne), puis travaille sur la copie écrite dans anonymise/.")


def _expand_braces(pattern: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    return [x for alt in m.group(1).split(",") for x in _expand_braces(pattern[:m.start()] + alt + pattern[m.end():])]


class TooBig(Exception):
    """A folder too large to check in time: the guard denies rather than guess."""


WALK_LIMIT = 5000
DEADLINE = time.monotonic() + 20  # stay well under the 60 s hook timeout


def _walk(base: Path, exts: set[str]):
    """Originals under base. Raises TooBig past WALK_LIMIT entries or the time budget."""
    n = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
        for f in filenames:
            n += 1
            if n > WALK_LIMIT or time.monotonic() > DEADLINE:
                raise TooBig(str(base))
            p = Path(dirpath) / f
            if p.suffix.lower() in exts and is_raw(p):
                yield p


def _label(base: Path, cwd: str) -> str:
    return _rel(base, cwd) if str(base) != cwd else "le dossier courant"


def check_grep(inp: dict, cwd: str) -> dict | None:
    base = resolve(inp.get("path") or ".", cwd)
    if base.is_file():
        return deny(f"{base.name} est un document client original. {HOW}") if is_raw(base) else None
    if not base.is_dir():
        return None
    g = inp.get("glob")
    typ = (inp.get("type") or "").lower()
    pats = _expand_braces(g) if g else []
    for p in _walk(base, TEXT_GUARDED):
        if typ and typ not in ("csv", "tsv"):
            continue
        if pats:
            neg = [x[1:] for x in pats if x.startswith("!")]
            pos = [x for x in pats if not x.startswith("!")]
            if neg and any(fnmatch.fnmatch(p.name, x) for x in neg):
                continue
            if pos and not any(fnmatch.fnmatch(p.name, x) or fnmatch.fnmatch(str(p), x) for x in pos):
                continue
        return deny(f"la recherche dans {_label(base, cwd)} lirait des documents clients originaux. "
                    "Exclus-les avec glob (\"!*.csv\") ou cherche dans les copies de anonymise/.")
    return None


def _segments(command: str) -> list[list[str]]:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        toks = command.replace(";", " ; ").replace("|", " | ").replace("&", " & ").split()
    segs, cur = [], []
    for t in toks:
        if t in SEPARATORS:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def _program(seg: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(seg) and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", seg[i]) or os.path.basename(seg[i]) in WRAPPERS):
        i += 1
    if i >= len(seg):
        return "", []
    return os.path.basename(seg[i]), seg[i + 1:]


GIT_DUMPERS = {"diff", "show", "log", "grep", "blame", "annotate", "cat-file", "format-patch", "whatchanged",
               "stash", "archive"}


def _git_sub(args: list[str]) -> str:
    return next((a for a in args if not a.startswith("-")), "")


def _git_dumps(args: list[str]) -> bool:
    sub = _git_sub(args)
    if sub in ("log", "whatchanged"):  # only with a patch: plain log prints messages, not file content
        return any(a in ("-p", "-u", "--patch", "--patch-with-stat", "--patch-with-raw") or a.startswith("-L")
                   for a in args)
    if sub == "stash":
        return "show" in args
    return sub in GIT_DUMPERS


def _repo_root(base: Path) -> Path:
    for d in [base, *base.parents]:
        if (d / ".git").exists():
            return d
    return base


def _seg_safe(prog: str, args: list[str]) -> bool:
    if prog == "git":
        return not _git_dumps(args)
    if prog == "find":
        return not any(a in ("-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fls") for a in args)
    return prog in SAFE_PROGRAMS


def _dir_raw(base: Path) -> Path | None:
    return next(_walk(base, GUARDED), None)


def check_bash(cmd: str, cwd: str) -> dict | None:
    segs = _segments(cmd)
    if ".anonymize-data" in cmd or str(home()) in cmd:
        if not all(_program(s)[0] == "anonymiser" for s in segs if s):
            return deny("le registre des copies ne se modifie pas à la main.")
    # every directory the command may run from: the session cwd and any `cd` target
    bases = [Path(cwd)]
    for s in segs:
        prog, args = _program(s)
        if prog == "cd" and args:
            bases.append(resolve(args[0], cwd))
    named: list[Path] = []   # originals the command names itself (safe to name back)
    hidden: list[Path] = []  # originals found by expanding a glob or a folder (never named to Claude)

    def check_ref(ref: str):
        for b in bases:
            if any(c in ref for c in "*?["):
                hits = glob.glob(str(resolve(ref, str(b))), recursive=True)[:2000]
                hidden.extend(Path(h) for h in hits if is_raw(Path(h)))
            else:
                p = resolve(ref, str(b))
                if is_raw(p):
                    named.append(p)

    for m in RE_GUARDED_REF.finditer(cmd):
        check_ref(m.group().strip("'\""))
    for tok in re.findall(r"[^\s'\"`;&|<>()]*[*?][^\s'\"`;&|<>()]*", cmd):
        if not RE_GUARDED_REF.fullmatch(tok):
            check_ref(tok)
    # a program that is not known to be harmless, given a folder that holds originals
    for s in segs:
        prog, args = _program(s)
        if not prog or _seg_safe(prog, args):
            continue
        dirs = [a for a in args if not a.startswith("-")]
        exts = GUARDED
        if prog == "find":
            dirs = dirs[:1] or ["."]
        elif prog == "git":  # diff, show, log -p... print the content of tracked text files
            exts = TEXT_GUARDED
            paths = [a for a in dirs[1:] if any(resolve(a, str(b)).exists() for b in bases)]
            dirs = paths or [str(_repo_root(b)) for b in bases]  # a ref alone (HEAD) covers the whole repo
        for a in dirs:
            for b in bases:
                d = resolve(a, str(b))
                if d.is_dir():
                    hit = next(_walk(d, exts), None)
                    if hit:
                        hidden.append(hit)
                        break
    if not named and not hidden:
        return None
    what = f"{named[0].name}, un document client original" if named else "des documents clients originaux"
    if "$(" in cmd or "`" in cmd or "<<" in cmd:
        return deny(f"la commande toucherait {what}. {HOW}")
    for s in segs:
        prog, args = _program(s)
        if prog and not _seg_safe(prog, args):
            return deny(f"`{prog}` ouvrirait {what}. {HOW}")
    return None


def on_tool(data: dict) -> dict | None:
    name = data.get("tool_name") or ""
    inp = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if name in ("Read", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead", "Write"):
        p = inp.get("file_path") or inp.get("notebook_path")
        if not p:
            return None
        path = resolve(p, cwd)
        if in_home(path):
            return deny("le registre des copies ne se lit ni ne se modifie.")
        if name != "Write" and is_raw(path):
            return deny(f"{path.name} est un document client original. {HOW}")
        return None
    if name == "Grep":
        return check_grep(inp, cwd)
    if name == "Bash":
        return check_bash(inp.get("command") or "", cwd)
    return None


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.loads(sys.stdin.read() or "{}")
        out = on_prompt(data) if mode == "prompt" else on_tool(data) if mode == "tool" else None
        if mode not in ("prompt", "tool"):
            raise ValueError("mode inconnu")
    except TooBig as e:
        reason = (f"dossier trop gros pour être vérifié à temps ({_rel(Path(str(e)), os.getcwd())}) : "
                  "vise un sous-dossier ou des fichiers précis.")
        out = (deny(reason) if mode == "tool" else
               {"decision": "block", "reason": "anonymize-data : " + reason})
    except Exception as e:
        reason = f"garde en erreur ({type(e).__name__}) : action bloquée par précaution."
        out = (deny(reason) if mode == "tool" else
               {"decision": "block", "reason": "anonymize-data : " + reason})
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
