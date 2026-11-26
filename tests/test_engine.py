"""Engine and formats, on fictive data. Needs the engine environment (spaCy + fr_core_news_md):

    ~/.anonymize-data/venv/bin/python -m unittest discover -s tests -t .

Every case below leaked with the previous version (v2) of this plugin.
"""
import csv
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    import spacy  # noqa: F401
    import openpyxl
    HAVE_ENGINE = True
except ImportError:
    HAVE_ENGINE = False

from anonymizer import rules as R

IBAN = "FR76 3000 6000 0112 3456 7890 189"
NIR = "1 85 04 75 116 001 42"


class RulesTest(unittest.TestCase):
    """Validators and patterns (no spaCy)."""

    def test_validators(self):
        self.assertTrue(R.iban_ok(IBAN))
        self.assertFalse(R.iban_ok("FR76 3000 6000 0112 3456 7890 188"))
        self.assertTrue(R.luhn_ok("123456782"))
        self.assertTrue(R.nir_ok(NIR))
        self.assertTrue(R.nir_ok("185047511600142"))
        self.assertFalse(R.nir_ok("385047511600142"))

    def kinds(self, text):
        return {(text[s:e], k) for s, e, k in R.detect_patterns(text)}

    def test_phone_is_not_split_as_a_date(self):
        self.assertIn(("06 12 34 56 78", "TEL"), self.kinds("Tel : 06 12 34 56 78"))
        self.assertIn(("+33 6 12 34 56 78", "TEL"), self.kinds("Tel : +33 6 12 34 56 78"))

    def test_siren_with_or_without_context_but_not_amounts(self):
        self.assertIn(("123 456 782", "SIREN"), self.kinds("SIREN 123 456 782"))
        self.assertIn(("123456782", "SIREN"), self.kinds("société 123456782 immatriculée"))
        self.assertFalse(self.kinds("Chiffre d'affaires : 123 456 789 euros"))
        self.assertFalse(self.kinds("Total 123 456 782 €"))

    def test_iban_stops_at_the_next_word(self):
        self.assertIn((IBAN, "IBAN"), self.kinds(f"IBAN {IBAN} BIC BNPAFRPP"))

    def test_dates_kept_except_birth(self):
        k = self.kinds("Née le 12/03/1985, facture du 14/12/2026")
        self.assertIn(("12/03/1985", "DATE_NAISSANCE"), k)
        self.assertNotIn("14/12/2026", {x for x, _ in k})

    def test_names_in_bank_lines(self):
        t = "VIR SEPA KARIM BENALI LOYER NOVEMBRE"
        self.assertIn(("KARIM BENALI", "PERSONNE"), {(t[s:e], k) for s, e, k in R.detect_names(t)})
        t = "VIR SEPA M. KARIM BENALI LOYER"
        self.assertIn(("KARIM BENALI", "PERSONNE"), {(t[s:e], k) for s, e, k in R.detect_names(t)})
        t = "Salarié : DUPONT Jean, matricule 00451"
        self.assertIn(("DUPONT Jean", "PERSONNE"), {(t[s:e], k) for s, e, k in R.detect_names(t)})

    def test_companies(self):
        t = "PRLV SEPA Boulangerie Martin SARL facture 2026-114"
        self.assertIn(("Boulangerie Martin SARL", "SOCIETE"), {(t[s:e], k) for s, e, k in R.detect_orgs(t)})


@unittest.skipUnless(HAVE_ENGINE, "moteur non installé (spaCy, openpyxl)")
class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from anonymizer.engine import Pseudonymizer
        cls.P = Pseudonymizer

    def check(self, text, forbidden, kept=(), **opts):
        out = self.P(**opts).process_one(text)
        for f in forbidden:
            self.assertNotIn(f, out, f"{f!r} visible dans {out!r}")
        for k in kept:
            self.assertIn(k, out, f"{k!r} perdu dans {out!r}")
        return out

    def test_payslip(self):
        self.check(f"Bulletin de paie. Salarié : DUPONT Jean, matricule 00451.\nAdresse : 14 rue de la Paix 75001 "
                   f"Paris. Email : jean.dupont@exemple.fr\nIBAN : {IBAN}. N° SS : {NIR}\nSalaire brut : 3 250,00 € "
                   f"du 01/11/2026 au 30/11/2026.",
                   ["DUPONT", "Jean", "00451", "Paix", "75001", "jean.dupont", "FR76", "116 001"],
                   ["Salaire brut : 3 250,00 €", "01/11/2026", "30/11/2026"])

    def test_bank_lines(self):
        self.check("VIR SEPA KARIM BENALI LOYER NOVEMBRE", ["KARIM", "BENALI"], ["LOYER NOVEMBRE"])
        self.check("VIR SEPA M. KARIM BENALI LOYER NOVEMBRE", ["KARIM", "BENALI"])
        self.check("VIR SEPA TRANSPORTS VASSEUR FACT 2026-12", ["VASSEUR"], ["2026-12"])
        self.check("PRLV SEPA FREE MOBILE FACTURE 112233", [], ["FREE MOBILE"])
        self.check("CB CARREFOUR LILLE 12/11", [], ["CARREFOUR", "12/11"])

    def test_companies_masked_or_kept(self):
        self.check("PRLV SEPA Boulangerie Martin SARL facture 2026-114", ["Martin"], ["2026-114"])
        self.check("Client : Transports Vasseur SAS, SIREN 123 456 782, gérant Olivier Vasseur.",
                   ["Vasseur", "123 456 782", "Olivier"])
        out = self.check("Client : Transports Vasseur SAS, gérant Olivier Vasseur.", ["Olivier"], keep_orgs=True)
        self.assertIn("SAS", out)

    def test_no_over_masking(self):
        self.check("Virement de Mme Claire Lefebvre pour la facture du cabinet", ["Claire", "Lefebvre"],
                   ["pour la facture du cabinet"])
        self.check("Chiffre d'affaires de l'exercice : 123 456 789 euros", [], ["123 456 789 euros"])

    def test_same_person_same_token_everywhere(self):
        p = self.P()
        a, b = p.process(["gérant Olivier Vasseur", "Le dossier Vasseur est à relancer. M. VASSEUR a appelé."])
        tok = a.split()[-1]
        self.assertTrue(tok.startswith("[PERSONNE_"), a)
        self.assertEqual(b.count(tok), 2, b)

    def test_uppercase_names(self):
        self.check("MARTIN Sophie et LEFEBVRE Paul ont signé le contrat.", ["Sophie", "LEFEBVRE", "Paul"])


# ---------------------------------------------------------------- formats, end to end

def make_docx(path: Path, body: list[str], header: str, comment: str):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    paras = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in body)
    tbl = ("<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Nom</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Sophie Martin"
           "</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{paras}{tbl}</w:body></w:document>")
        z.writestr("word/header1.xml", f"<w:hdr {W}><w:p><w:r><w:t>{header}</w:t></w:r></w:p></w:hdr>")
        z.writestr("word/comments.xml", f"<w:comments {W}><w:comment><w:p><w:r><w:t>{comment}</w:t></w:r></w:p>"
                                        f"</w:comment></w:comments>")
        z.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Jean Dupont</dc:creator></cp:coreProperties>")


def make_pptx(path: Path, slide: str, note: str):
    A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ppt/slides/slide1.xml", f"<p:sld {A} xmlns:p='p'><a:p><a:r><a:t>{slide}</a:t></a:r></a:p></p:sld>")
        z.writestr("ppt/notesSlides/notesSlide1.xml", f"<p:notes {A} xmlns:p='p'><a:p><a:r><a:t>{note}</a:t></a:r>"
                                                      f"</a:p></p:notes>")

def make_pdf(path: Path, lines: list[str]):
    """A minimal PDF with a text layer (Helvetica, WinAnsi)."""
    content = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(
        "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for l in lines) + " ET"
    data = content.encode("cp1252")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(data)).encode() + b" >>stream\n" + data + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")


def make_scan(path: Path, lines: list[str]):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1700, 600), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(FONT), 44)
    for i, l in enumerate(lines):
        d.text((60, 60 + i * 80), l, fill="black", font=f)
    img.save(path)


def have_ocr():
    try:
        import pytesseract
        return "fra" in pytesseract.get_languages(config="") and FONT.exists()
    except Exception:
        return False


@unittest.skipUnless(HAVE_ENGINE, "moteur non installé (spaCy, openpyxl)")
class FormatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        os.environ["ANONYMIZE_DATA_HOME"] = str(self.d / "home")
        self.out = self.d / "anonymise"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *paths, **opts):
        from anonymizer.cli import run
        return run([Path(p) for p in paths], self.out, **opts)

    def test_xlsx_columns_numbers_and_short_cells(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Paie DUPONT"
        ws.append(["Salarié", "Client", "Libellé", "Téléphone", "Numéro sécu", "Nombre d'heures", "Contribution",
                   "Montant"])
        ws.append(["Dupont", "Transports Vasseur SAS", "Loyer Mme Lefebvre", 612345678, 185047511600142, 151.67,
                   120.5, 3250])
        ws.append(["Jean Dupont", "EDF", "VIR M. KARIM BENALI", "06 12 34 56 78", NIR, 140, 98.2, 2900])
        src = self.d / "Paie_DUPONT_2026.xlsx"
        wb.save(src)
        res = self.run_cli(src)
        self.assertFalse(res["erreurs"], res)
        out = Path(res["produits"][0]["sortie"])
        self.assertNotIn("DUPONT", out.name)
        wb2 = openpyxl.load_workbook(out)
        ws2 = wb2.worksheets[0]
        self.assertNotIn("DUPONT", ws2.title)
        flat = json.dumps([[c for c in r] for r in ws2.iter_rows(values_only=True)], ensure_ascii=False)
        for f in ["Dupont", "Vasseur", "Lefebvre", "KARIM", "BENALI", "612345678", "185047511600142", "116 001",
                  "06 12"]:
            self.assertNotIn(f, flat, flat)
        rows = list(ws2.iter_rows(values_only=True))
        self.assertEqual(rows[0], ("Salarié", "Client", "Libellé", "Téléphone", "Numéro sécu", "Nombre d'heures",
                                   "Contribution", "Montant"))
        self.assertEqual(rows[1][5:], (151.67, 120.5, 3250))
        self.assertEqual(rows[2][1], "EDF")
        self.assertEqual(rows[1][0], rows[2][0], "le même salarié doit garder le même repère")

    def test_csv_semicolon(self):
        src = self.d / "releve.csv"
        src.write_text("Date;Libellé;Montant\n01/11/2026;VIR SEPA KARIM BENALI LOYER;-850,00\n"
                       "02/11/2026;PRLV SEPA URSSAF;-312,00\n", encoding="cp1252")
        res = self.run_cli(src)
        out = Path(res["produits"][0]["sortie"])
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0], ["Date", "Libellé", "Montant"])
        self.assertNotIn("BENALI", rows[1][1])
        self.assertEqual(rows[1][2], "-850,00")
        self.assertEqual(rows[2][1], "PRLV SEPA URSSAF")

    def test_docx_header_table_comment_no_metadata(self):
        src = self.d / "contrat.docx"
        make_docx(src, ["Contrat entre Madame Sophie MARTIN et la société Vasseur SAS.", f"IBAN {IBAN}"],
                  "Dossier Martin, tél 06 12 34 56 78", "Vérifier avec M. Olivier Vasseur")
        res = self.run_cli(src)
        text = Path(res["produits"][0]["sortie"]).read_text(encoding="utf-8")
        for f in ["Sophie", "MARTIN", "Martin", "Vasseur", "Olivier", "FR76", "06 12", "Jean Dupont"]:
            self.assertNotIn(f, text, text)
        self.assertIn("En-tête", text)
        self.assertIn("Commentaires", text)

    def test_pptx_slide_and_notes(self):
        src = self.d / "deck.pptx"
        make_pptx(src, "Proposition pour Mme Claire Lefebvre", "Appeler Claire au 06 12 34 56 78")
        res = self.run_cli(src)
        text = Path(res["produits"][0]["sortie"]).read_text(encoding="utf-8")
        for f in ["Claire", "Lefebvre", "06 12"]:
            self.assertNotIn(f, text, text)
        self.assertIn("Notes", text)

    def test_folder_run_is_consistent_and_registered(self):
        (self.d / "a.txt").write_text("Gérant : Olivier Vasseur", encoding="utf-8")
        (self.d / "b.txt").write_text("Relancer M. Vasseur", encoding="utf-8")
        res = self.run_cli(self.d)
        outs = {Path(p["source"]).name: Path(p["sortie"]).read_text(encoding="utf-8") for p in res["produits"]}
        tok = outs["a.txt"].split()[-1]
        self.assertIn(tok, outs["b.txt"])
        reg = (self.d / "home" / "produits.txt").read_text().split()
        self.assertEqual(len(reg), 2)

    def test_pdf_text_layer(self):
        src = self.d / "bulletin.pdf"
        make_pdf(src, ["Bulletin de paie novembre 2026", "Salarié : DUPONT Jean", f"IBAN : {IBAN}",
                       f"N° SS : {NIR}", "Salaire brut : 3 250,00 EUR"])
        res = self.run_cli(src)
        self.assertFalse(res["erreurs"], res)
        text = Path(res["produits"][0]["sortie"]).read_text(encoding="utf-8")
        for f in ["DUPONT", "Jean", "FR76", "116 001"]:
            self.assertNotIn(f, text, text)
        self.assertIn("3 250,00", text)
        self.assertIn("## Page 1", text)

    @unittest.skipUnless(have_ocr(), "OCR non installé")
    def test_scanned_pdf_and_photo_go_through_ocr(self):
        lines = ["Bulletin de paie", "Salarie : DUPONT Jean", "Telephone : 06 12 34 56 78", f"IBAN : {IBAN}"]
        png = self.d / "photo.png"
        make_scan(png, lines)
        from PIL import Image
        pdf = self.d / "scan.pdf"
        Image.open(png).save(pdf)
        res = self.run_cli(png, pdf)
        self.assertFalse(res["erreurs"], res)
        for p in res["produits"]:
            text = Path(p["sortie"]).read_text(encoding="utf-8")
            self.assertIn("Bulletin", text, "l'OCR n'a rien lu")
            for f in ["DUPONT", "Jean", "06 12", "FR76"]:
                self.assertNotIn(f, text, text)

    def test_errors_never_quote_content(self):
        src = self.d / "faux.xlsx"
        src.write_bytes(b"Jean Dupont FR76 pas un classeur")
        res = self.run_cli(src)
        msg = json.dumps(res, ensure_ascii=False)
        self.assertTrue(res["erreurs"])
        self.assertNotIn("Dupont", msg.replace(str(src), ""))

    def test_unsupported_format_is_refused(self):
        src = self.d / "vieux.xls"
        src.write_bytes(b"x")
        res = self.run_cli(src)
        self.assertIn("xlsx", res["erreurs"][0]["message"])


if __name__ == "__main__":
    unittest.main()
