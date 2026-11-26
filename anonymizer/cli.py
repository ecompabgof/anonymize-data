"""anonymiser: write pseudonymised copies of client files, locally.

    anonymiser FICHIER_OU_DOSSIER... [--sortie DOSSIER] [--garder-societes] [--masquer-dates] [--json]

Nothing is sent anywhere. The copies land in ./anonymise (or --sortie) and their
fingerprints are recorded so the Claude Code guard lets Claude read them, and only them.
Messages never quote document content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: python anonymizer/cli.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "anonymizer"

from anonymizer import formats as F  # noqa: E402
from anonymizer import rules as R  # noqa: E402
from anonymizer.engine import NAME_KINDS, EngineError, Pseudonymizer  # noqa: E402

LABELS = {
    "PERSONNE": "personnes", "SOCIETE": "sociétés", "TIERS": "tiers", "EMAIL": "e-mails", "TEL": "téléphones",
    "IBAN": "IBAN", "NIR": "n° de sécu", "CARTE": "cartes", "SIRET": "SIRET", "SIREN": "SIREN", "TVA": "n° TVA",
    "ADRESSE": "adresses", "CP_VILLE": "codes postaux", "DATE_NAISSANCE": "dates de naissance",
    "MATRICULE": "matricules", "URL": "liens", "IP": "adresses IP", "DATE": "dates",
    "balayage": "noms repris ailleurs", "rattrapés": "rattrapés au contrôle final",
}


def home() -> Path:
    return Path(os.environ.get("ANONYMIZE_DATA_HOME", Path.home() / ".anonymize-data"))


def registry() -> Path:
    return home() / "produits.txt"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register(path: Path):
    reg = registry()
    reg.parent.mkdir(parents=True, exist_ok=True)
    with reg.open("a", encoding="utf-8") as f:
        f.write(sha256(path) + "\n")
    try:
        os.chmod(reg, 0o600)
    except OSError:
        pass


def produced() -> set[str]:
    try:
        return set(registry().read_text(encoding="utf-8").split())
    except OSError:
        return set()


def collect(paths: list[Path], out_dir: Path) -> list[Path]:
    files = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if (f.is_file() and not any(x.startswith(".") for x in f.relative_to(p).parts)
                        and out_dir.resolve() not in f.resolve().parents
                        and f.suffix.lower() in F.SUPPORTED | set(F.UNSUPPORTED_HINT)):
                    files.append(f)
        else:
            files.append(p)
    return files


def _table_plan(u: F.Unit, keep_orgs: bool):
    """Classify columns; return (free-text cells, preset values) with back references."""
    texts, refs, presets = [], [], []
    for si, sh in enumerate(u.sheets):
        texts.append(sh.name)
        refs.append(("sheet", si, None, None))
        sh.header = F.find_header(sh.rows)
        if sh.header is not None:
            for ci, h in enumerate(sh.rows[sh.header]):
                k = F.column_kind(h)
                if k:
                    sh.kinds[ci] = k
        for ri, row in enumerate(sh.rows):
            for ci, v in enumerate(row):
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                kind = sh.kinds.get(ci) if sh.header is not None and ri > sh.header else None
                if kind == "TIERS":
                    kind = _tiers_kind(str(v), keep_orgs)
                    row[ci] = ("__KIND__", kind, v) if kind else v
                    if kind:
                        presets.append((str(v), kind))
                    elif isinstance(v, str):
                        texts.append(v)
                        refs.append(("cell", si, ri, ci))
                    continue
                if kind:
                    row[ci] = ("__KIND__", kind, v)
                    presets.append((_fmt(v), kind))
                elif isinstance(v, str):
                    texts.append(v)
                    refs.append(("cell", si, ri, ci))
                else:
                    nk = F.numeric_kind(v)
                    if nk:
                        row[ci] = ("__KIND__", nk, v)
                        presets.append((_fmt(v), nk))
    return texts, refs, presets


def _fmt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _tiers_kind(v: str, keep_orgs: bool) -> str | None:
    if any(k == "PERSONNE" for _, _, k in R.detect_names(v)):
        return "PERSONNE"
    if R._known_org(v):
        return None
    if keep_orgs and (R.RE_ORG_SUFFIX.search(v) or R.RE_ORG_PREFIX.search(v)):
        return None
    return "TIERS" if keep_orgs else "SOCIETE"


def run(paths: list[Path], out_dir: Path, keep_orgs=False, mask_dates=False, use_ner=True) -> dict:
    result = {"produits": [], "erreurs": [], "avertissements": []}
    files = collect(paths, out_dir)
    if not files:
        result["erreurs"].append({"source": "", "message": "aucun fichier à traiter"})
        return result
    units = []
    for f in files:
        try:
            if not f.is_file():
                raise EngineError("fichier introuvable")
            units.append(F.read(f))
        except EngineError as e:
            result["erreurs"].append({"source": str(f), "message": str(e)})
        except Exception as e:  # never echo third-party messages: they can quote content
            result["erreurs"].append({"source": str(f), "message": f"lecture impossible ({type(e).__name__})"})
    if not units:
        return result

    pz = Pseudonymizer(keep_orgs=keep_orgs, mask_dates=mask_dates, use_ner=use_ner)
    texts, refs, presets = [], [], []
    plans = {}
    for ui, u in enumerate(units):
        if u.is_table:
            t, r, p = _table_plan(u, keep_orgs)
            plans[ui] = (len(texts), len(t))
            texts += t
            refs += [(ui,) + x for x in r]
            presets += p
        else:
            plans[ui] = (len(texts), len(u.blocks))
            texts += u.blocks
            refs += [(ui, "block", i, None, None) for i in range(len(u.blocks))]
    before = dict(pz.found)
    outs = pz.process(texts, presets)
    names = pz.process([u.source.stem.replace("_", " ").replace("-", " ") for u in units])

    out_dir.mkdir(parents=True, exist_ok=True)
    taken = set()
    for ui, u in enumerate(units):
        start, n = plans[ui]
        mine = outs[start:start + n]
        stem = F.safe_name(names[ui])
        target = out_dir / f"{stem}.anon{u.out_ext}"
        k = 2
        while target in taken or (target.exists() and not _ours(target)):
            target = out_dir / f"{stem}-{k}.anon{u.out_ext}"
            k += 1
        taken.add(target)
        try:
            if u.is_table:
                sheets = _rebuild(u, refs[start:start + n], mine, pz)
                if u.out_ext == ".xlsx":
                    F.write_xlsx(sheets, target)
                else:
                    F.write_csv(sheets[0][1], target, u.delimiter)
            else:
                F.write_markdown(u, mine, target)
            register(target)
            result["produits"].append({"source": str(u.source), "sortie": str(target)})
            for w in u.warnings:
                result["avertissements"].append({"source": str(u.source), "message": w})
        except Exception as e:
            result["erreurs"].append({"source": str(u.source), "message": f"écriture impossible ({type(e).__name__})"})
    result["compte"] = {k: v - before.get(k, 0) for k, v in pz.found.items() if v - before.get(k, 0) > 0}
    return result


def _ours(path: Path) -> bool:
    try:
        return sha256(path) in produced()
    except OSError:
        return False


def _rebuild(u: F.Unit, refs, outs, pz: Pseudonymizer):
    sheets = [[sh.name, sh.rows] for sh in u.sheets]
    for ref, val in zip(refs, outs):
        _, what, si, ri, ci = ref
        if what == "sheet":
            sheets[si][0] = F.safe_name(val) if val != u.sheets[si].name else val
        else:
            sheets[si][1][ri][ci] = val
    for s in sheets:
        for row in s[1]:
            for ci, v in enumerate(row):
                if isinstance(v, tuple) and len(v) == 3 and v[0] == "__KIND__":
                    row[ci] = pz.token_for(v[1], _fmt(v[2]))
                    pz.found[v[1]] += 1
    return [(n, rows) for n, rows in sheets]


def human(result: dict) -> str:
    lines = []
    for p in result["produits"]:
        lines.append(f"OK  {p['source']}\n    -> {p['sortie']}")
    if result.get("compte"):
        lines.append("Remplacés : " + ", ".join(f"{v} {LABELS.get(k, k)}" for k, v in sorted(result["compte"].items())))
    for a in result["avertissements"]:
        lines.append(f"ATTENTION  {a['source']} : {a['message']}")
    for e in result["erreurs"]:
        lines.append(f"ERREUR  {e['source']} : {e['message']}")
    if result["produits"]:
        lines.append("Relis la copie avant de t'en servir : la détection n'est pas parfaite.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="anonymiser", description=__doc__.split("\n\n")[0])
    ap.add_argument("chemins", nargs="+", type=Path)
    ap.add_argument("--sortie", type=Path, default=Path("anonymise"))
    ap.add_argument("--garder-societes", action="store_true", help="laisser les noms de sociétés visibles")
    ap.add_argument("--masquer-dates", action="store_true", help="masquer aussi les dates ordinaires")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = run(a.chemins, a.sortie, a.garder_societes, a.masquer_dates)
    except EngineError as e:
        res = {"produits": [], "avertissements": [], "erreurs": [{"source": "", "message": str(e)}]}
    except Exception as e:
        res = {"produits": [], "avertissements": [],
               "erreurs": [{"source": "", "message": f"erreur interne ({type(e).__name__})"}]}
    print(json.dumps(res, ensure_ascii=False) if a.json else human(res))
    return 0 if res["produits"] and not res["erreurs"] else 1


if __name__ == "__main__":
    sys.exit(main())
