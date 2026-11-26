"""Readers and writers. Each reader turns a file into a Unit: text blocks, or sheets of rows.

Text documents (pdf, images, docx, pptx, txt, md) come out as Markdown.
Tables (xlsx, csv, tsv) keep their rows and columns.
Office files are read from their XML parts, so headers, footers, notes, comments
and text boxes are all covered, and no metadata (author, revisions) is carried over.
"""
from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from . import rules as R
from .engine import EngineError

TEXT_EXT = {".txt", ".md"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif", ".avif"}
SUPPORTED = TEXT_EXT | IMAGE_EXT | {".pdf", ".docx", ".pptx", ".xlsx", ".xlsm", ".csv", ".tsv"}
UNSUPPORTED_HINT = {
    ".xls": "enregistre-le en .xlsx", ".ods": "enregistre-le en .xlsx", ".doc": "enregistre-le en .docx",
    ".odt": "enregistre-le en .docx", ".rtf": "enregistre-le en .docx", ".ppt": "enregistre-le en .pptx",
    ".odp": "enregistre-le en .pptx", ".eml": "exporte le mail en PDF", ".msg": "exporte le mail en PDF",
}


@dataclass
class Sheet:
    name: str
    rows: list[list]
    header: int | None = None
    kinds: dict[int, str] = field(default_factory=dict)


@dataclass
class Unit:
    source: Path
    out_ext: str
    blocks: list[str] = field(default_factory=list)
    headings: list[str | None] = field(default_factory=list)
    sheets: list[Sheet] = field(default_factory=list)
    delimiter: str = ","
    warnings: list[str] = field(default_factory=list)

    @property
    def is_table(self) -> bool:
        return self.out_ext in (".xlsx", ".csv", ".tsv")


# ---------------------------------------------------------------- text files

def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def read_text(path: Path) -> Unit:
    u = Unit(path, ".md")
    u.blocks = [_decode(path.read_bytes())]
    u.headings = [None]
    return u


# ---------------------------------------------------------------- OCR

def _tesseract():
    # On macOS, Leptonica rewrites paths that start with /tmp to the per-user temp folder, so pytesseract's
    # temp files under /tmp/... are "not found". The resolved path (/private/tmp/...) is left alone.
    import tempfile
    tempfile.tempdir = os.path.realpath(tempfile.gettempdir())
    try:
        import pytesseract
        langs = set(pytesseract.get_languages(config=""))
    except Exception as e:
        raise EngineError("OCR non installé : installe Tesseract (brew install tesseract tesseract-lang) "
                          "puis relance install.sh") from e
    lang = "+".join(x for x in ("fra", "eng") if x in langs) or None
    if lang is None:
        raise EngineError("Tesseract n'a ni le français ni l'anglais : installe tesseract-lang")
    return pytesseract, lang


def _ocr_image(img) -> str:
    pyt, lang = _tesseract()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return pyt.image_to_string(img, lang=lang)


def read_image(path: Path) -> Unit:
    try:
        from PIL import Image
    except ImportError as e:
        raise EngineError("Pillow n'est pas installé : lance install.sh") from e
    if path.suffix.lower() in (".heic", ".heif", ".avif"):
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError as e:
            raise EngineError("lecture HEIC/AVIF non installée (pillow-heif)") from e
    with Image.open(path) as img:
        text = _ocr_image(img)
    u = Unit(path, ".md")
    u.blocks, u.headings = [text], [None]
    if len(text.strip()) < 10:
        u.warnings.append("presque aucun texte lu sur l'image")
    return u


# ---------------------------------------------------------------- PDF

def read_pdf(path: Path) -> Unit:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise EngineError("pypdf n'est pas installé : lance install.sh") from e
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise EngineError("PDF protégé par un mot de passe : enlève la protection d'abord")
        pages = [(p.extract_text() or "") for p in reader.pages]
    except EngineError:
        raise
    except Exception as e:
        raise EngineError(f"PDF illisible ({type(e).__name__})") from e
    u = Unit(path, ".md")
    empty = [i for i, t in enumerate(pages) if len(t.strip()) < 30]
    if empty:
        try:
            import pypdfium2 as pdfium
            _tesseract()
            pdf = pdfium.PdfDocument(str(path))
            for i in empty:
                img = pdf[i].render(scale=300 / 72).to_pil()
                pages[i] = _ocr_image(img)
        except EngineError:
            if len(empty) == len(pages):
                raise EngineError("PDF scanné : l'OCR n'est pas installé (brew install tesseract tesseract-lang, "
                                  "puis install.sh)")
            u.warnings.append(f"{len(empty)} page(s) sans texte non lues (OCR non installé)")
        except ImportError:
            if len(empty) == len(pages):
                raise EngineError("PDF scanné : l'OCR n'est pas installé (pypdfium2 manquant, relance install.sh)")
            u.warnings.append(f"{len(empty)} page(s) sans texte non lues (OCR non installé)")
    u.blocks = pages
    u.headings = [f"## Page {i + 1}" for i in range(len(pages))]
    return u


# ---------------------------------------------------------------- DOCX / PPTX

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _wp_text(p) -> str:
    out = []
    for el in p.iter():
        if el.tag == W + "t" and el.text:
            out.append(el.text)
        elif el.tag == W + "tab":
            out.append("\t")
        elif el.tag in (W + "br", W + "cr"):
            out.append("\n")
    return "".join(out)


def read_docx(path: Path) -> Unit:
    u = Unit(path, ".md")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise EngineError("fichier .docx abîmé ou protégé") from e
    with z:
        names = z.namelist()
        body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
        for child in list(body) if body is not None else []:
            if child.tag == W + "p":
                t = _wp_text(child)
                if t.strip():
                    u.blocks.append(t)
                    u.headings.append(None)
            elif child.tag == W + "tbl":
                for tr in child.iter(W + "tr"):
                    cells = [" ".join(_wp_text(p) for p in tc.iter(W + "p")).strip() for tc in tr.findall(W + "tc")]
                    u.blocks.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
                    u.headings.append(None)
        extra = sorted(n for n in names if re.fullmatch(r"word/(header|footer)\d*\.xml|word/(footnotes|endnotes|"
                                                       r"comments)\.xml", n))
        for n in extra:
            texts = [_wp_text(p) for p in ET.fromstring(z.read(n)).iter(W + "p")]
            texts = [t for t in texts if t.strip()]
            if texts:
                label = {"header": "En-tête", "footer": "Pied de page", "footnotes": "Notes de bas de page",
                         "endnotes": "Notes de fin", "comments": "Commentaires"}[re.sub(r"\d|\.xml|word/", "", n)]
                for i, t in enumerate(texts):
                    u.blocks.append(t)
                    u.headings.append(f"## {label}" if i == 0 else None)
    return u


def _slide_no(name: str) -> int:
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def read_pptx(path: Path) -> Unit:
    u = Unit(path, ".md")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise EngineError("fichier .pptx abîmé ou protégé") from e

    def paras(xml: bytes) -> list[str]:
        out = []
        for p in ET.fromstring(xml).iter(A + "p"):
            t = "".join(el.text or "" for el in p.iter() if el.tag == A + "t")
            if t.strip():
                out.append(t)
        return out

    with z:
        names = z.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_slide_no)
        notes = {_slide_no(n): n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)}
        for n in slides:
            k = _slide_no(n)
            texts = paras(z.read(n))
            u.blocks.append("\n".join(texts))
            u.headings.append(f"## Diapositive {k}")
            if k in notes:
                nt = [t for t in paras(z.read(notes[k])) if not t.strip().isdigit()]
                if nt:
                    u.blocks.append("\n".join(nt))
                    u.headings.append("Notes :")
        for n in sorted(x for x in names if re.fullmatch(r"ppt/comments/.*\.xml", x)):
            root = ET.fromstring(z.read(n))
            texts = [el.text for el in root.iter() if el.tag.endswith("}text") and el.text]
            if texts:
                u.blocks.append("\n".join(texts))
                u.headings.append("## Commentaires")
    return u


# ---------------------------------------------------------------- tables

def read_xlsx(path: Path) -> Unit:
    try:
        import openpyxl
    except ImportError as e:
        raise EngineError("openpyxl n'est pas installé : lance install.sh") from e
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise EngineError(f"classeur illisible ({type(e).__name__})") from e
    u = Unit(path, ".xlsx")
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        while rows and all(v is None or (isinstance(v, str) and not v.strip()) for v in rows[-1]):
            rows.pop()
        u.sheets.append(Sheet(ws.title, rows))
    wb.close()
    return u


def _sniff(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    counts = {d: sample.count(d) for d in (";", ",", "\t", "|")}
    return max(counts, key=counts.get) if any(counts.values()) else ","


def read_csv(path: Path) -> Unit:
    text = _decode(path.read_bytes())
    delim = "\t" if path.suffix.lower() == ".tsv" else _sniff(text)
    u = Unit(path, ".tsv" if path.suffix.lower() == ".tsv" else ".csv", delimiter=delim)
    u.sheets.append(Sheet(path.stem, [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]))
    return u


READERS = {".pdf": read_pdf, ".docx": read_docx, ".pptx": read_pptx, ".xlsx": read_xlsx, ".xlsm": read_xlsx,
           ".csv": read_csv, ".tsv": read_csv}


def read(path: Path) -> Unit:
    ext = path.suffix.lower()
    if ext in UNSUPPORTED_HINT:
        raise EngineError(f"format {ext} non pris en charge : {UNSUPPORTED_HINT[ext]}")
    if ext in TEXT_EXT:
        return read_text(path)
    if ext in IMAGE_EXT:
        return read_image(path)
    if ext in READERS:
        return READERS[ext](path)
    raise EngineError(f"format {ext or 'sans extension'} non pris en charge")


# ---------------------------------------------------------------- column rules

COLUMN_PHRASES = [  # checked first, longest first
    ("TIERS", ["nom du client", "nom client", "nom du fournisseur", "nom fournisseur", "raison sociale",
               "nom commercial", "nom de l entreprise", "nom de la societe", "denomination", "contrepartie",
               "nom du tiers"]),
    ("EMAIL", ["adresse mail", "adresse email", "adresse e mail", "e mail"]),
    ("NIR", ["securite sociale", "numero de securite sociale", "numero ss", "n ss", "no ss", "n secu"]),
    ("DATE_NAISSANCE", ["date de naissance", "ne le", "nee le", "date of birth"]),
    ("TVA", ["numero de tva", "n tva intracommunautaire", "tva intracommunautaire", "tva intracom", "n tva",
             "numero tva", "vat number"]),
    ("ADRESSE", ["complement d adresse", "complement adresse", "adresse postale", "lieu de naissance"]),
    ("MATRICULE", ["carte d identite", "numero de permis", "n salarie", "numero salarie"]),
    ("PERSONNE", ["nom complet", "nom prenom", "nom et prenom", "prenom nom", "full name", "first name",
                  "last name", "nom de naissance", "nom d usage"]),
]
COLUMN_WORDS = [  # then single words, in this order
    ("EMAIL", {"email", "mail", "courriel", "emails"}),
    ("TEL", {"tel", "telephone", "portable", "mobile", "phone", "fax", "gsm"}),
    ("IBAN", {"iban", "rib", "bic", "swift"}),
    ("NIR", {"nir", "secu", "ss"}),
    ("SIRET", {"siret"}),
    ("SIREN", {"siren"}),
    ("DATE_NAISSANCE", {"naissance", "ddn", "birthdate", "birthday"}),
    ("MATRICULE", {"matricule", "cni", "passeport", "passport"}),
    ("ADRESSE", {"adresse", "address", "rue", "voie"}),
    ("TIERS", {"client", "clients", "fournisseur", "fournisseurs", "tiers", "contact", "destinataire", "emetteur",
               "expediteur", "payeur", "debiteur", "crediteur", "locataire", "proprietaire", "bailleur", "customer",
               "supplier", "vendor", "payee", "beneficiaire", "donneur"}),
    ("PERSONNE", {"nom", "prenom", "prenoms", "salarie", "salariee", "employe", "employee", "collaborateur",
                  "collaboratrice", "titulaire", "interlocuteur", "gerant", "dirigeant", "associe", "signataire",
                  "conjoint", "enfant", "name", "firstname", "lastname", "surname", "patient", "eleve"}),
]


def column_kind(header) -> str | None:
    if not isinstance(header, str) or not header.strip():
        return None
    h = " " + re.sub(r"[^a-z0-9]+", " ", R.fold(header)).strip() + " "
    for kind, phrases in COLUMN_PHRASES:
        for p in sorted(phrases, key=len, reverse=True):
            if f" {p} " in h:
                return kind
    words = set(h.split())
    for kind, keys in COLUMN_WORDS:
        if words & keys:
            return kind
    return None


def find_header(rows: list[list]) -> int | None:
    for i, row in enumerate(rows[:10]):
        vals = [v for v in row if v is not None and str(v).strip()]
        if len(vals) >= 2 and sum(isinstance(v, str) and not R.digits(v) == v.strip() for v in vals) / len(vals) >= .6:
            return i
    return None


def cell_text(v) -> str | None:
    if isinstance(v, str):
        return v
    return None


def numeric_kind(v) -> str | None:
    """A number that is in fact an identifier (NIR or card stored as a number)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if isinstance(v, float) and not v.is_integer():
        return None
    s = str(int(v))
    if len(s) in (13, 15) and R.nir_ok(s):
        return "NIR"
    if len(s) in (15, 16) and R.luhn_ok(s):
        return "CARTE"
    return None


# ---------------------------------------------------------------- writers

def safe_name(text: str) -> str:
    t = re.sub(r"\[([A-Z_]+)_(\d+)\]", r"\1-\2", text)
    t = re.sub(r"[^\w\-.]+", "_", t, flags=re.UNICODE).strip("._")
    return t[:80] or "document"


def write_markdown(u: Unit, blocks: list[str], out: Path):
    parts = []
    for h, b in zip(u.headings, blocks):
        if h:
            parts.append(h)
        parts.append(b.rstrip())
    out.write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")


def _sheet_title(name: str, used: set) -> str:
    t = re.sub(r"[\[\]:*?/\\]", "-", name)[:31] or "Feuille"
    base, n = t, 2
    while t in used:
        t = f"{base[:28]}-{n}"
        n += 1
    used.add(t)
    return t


def write_xlsx(sheets: list[tuple[str, list[list]]], out: Path):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    used = set()
    for name, rows in sheets:
        ws = wb.create_sheet(_sheet_title(name, used))
        for r in rows:
            ws.append([v if isinstance(v, (str, int, float, bool, date, datetime)) or v is None else str(v)
                       for v in r])
    wb.save(out)


def write_csv(rows: list[list], out: Path, delimiter: str):
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=delimiter).writerows(rows)
