"""Pattern rules, validators and word lists for French documents.

Everything here is pure standard library so it can be tested without spaCy.
Each rule returns spans (start, end, kind) over the original text.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"

# Kinds, in priority order when spans overlap (first wins).
PRIORITY = [
    "EMAIL", "IBAN", "NIR", "CARTE", "SIRET", "SIREN", "TVA", "TEL", "URL", "IP",
    "DATE_NAISSANCE", "MATRICULE", "PERSONNE", "SOCIETE", "TIERS", "ADRESSE", "CP_VILLE", "DATE",
]
RANK = {k: i for i, k in enumerate(PRIORITY)}


def fold(s: str) -> str:
    """Lowercase, strip accents and collapse spaces: the comparison key for words."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def digits(s: str) -> str:
    return re.sub(r"\D", "", s)


# ---------------------------------------------------------------- validators

def luhn_ok(num: str) -> bool:
    if not num.isdigit() or len(num) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_ok(s: str) -> bool:
    s = re.sub(r"\s", "", s).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def nir_ok(s: str) -> bool:
    """Structure check of a French social security number (13 digits, or 15 with the key)."""
    c = re.sub(r"[\s.]", "", s).upper()
    if len(c) not in (13, 15) or c[0] not in "12":
        return False
    month = c[3:5]
    if not month.isdigit() or not (1 <= int(month) <= 12 or 20 <= int(month) <= 99):
        return False
    if len(c) == 15:
        body = c[:13].replace("2A", "19").replace("2B", "18")
        if not body.isdigit() or not c[13:].isdigit():
            return False
        return True  # the key is not checked: a mistyped NIR is still a NIR
    return c[:13].replace("2A", "19").replace("2B", "18").isdigit()


# ---------------------------------------------------------------- word lists

@lru_cache(maxsize=None)
def first_names() -> frozenset[str]:
    words = set()
    for line in (DATA / "first_names.txt").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        words.update(fold(w) for w in line.split())
    return frozenset(words)


# First names that are also common words or places: never masked on their own.
AMBIGUOUS_FIRST_NAMES = frozenset(fold(w) for w in """
France Paris Marine Rose Olive Lune Fleur Victoire Constant Prudence Ange Aime Desire Grace Avril
Mai Juin Lys Iris Jade Perle Ambre Capucine Violette Prune Cerise Colombe Bleu Max Sam Clement Leger
Petit Blanc Noel Roi Gai Aimee Sage Rocher Prosper Fidele Felicite Clemence Esperance Celeste Dominique
""".split())

# Words that can never be part of a person name (uppercase banking and business vocabulary).
NAME_STOP = frozenset(fold(w) for w in """
vir virement virements sepa prlv prelevement prelevements cb carte cartes cheque cheques chq rem remise retrait
dab frais commission commissions cotisation cotisations loyer loyers facture factures fact fac fct avoir acompte
solde salaire salaires paie prime primes remboursement remb echeance echeances pret credit debit tva ht ttc
eur euro euros ref reference motif libelle janvier fevrier mars avril mai juin juillet aout septembre
octobre novembre decembre janv fevr fev juil sept oct nov dec pour par de du des le la les et en au aux a sur
client clients fournisseur fournisseurs salarie salaries contact adresse email mail tel telephone iban bic
siret siren nir matricule bulletin contrat devis commande livraison total montant net brut numero no n date
periode exercice bilan cabinet societe entreprise sas sasu sarl sa sci eurl snc scp selarl selas scm scop gie
eirl ei boulangerie pharmacie garage restaurant hotel cafe bar tabac boucherie inst instantane recu emis
permanent europeen faveur ordre dont avec chez via objet madame monsieur mademoiselle mme mlle
urssaf dgfip impots cpam caf msa retraite mutuelle prevoyance assurance banque agence service services groupe
holding transports transport conseil conseils expertise audit immobilier immo bureau bureaux page annexe
la poste free orange sfr bouygues edf engie amazon google apple microsoft paypal stripe uber
""".split())

# Banking vocabulary that ends a counterparty after VIR / PRLV.
BANK_STOP = frozenset(fold(w) for w in """
vir virement sepa prlv prelevement cb carte cheque chq rem remise retrait frais commission cotisation cotisations
loyer loyers facture factures fact fac fct avoir acompte solde salaire salaires paie prime remboursement remb
echeance pret credit debit tva ht ttc eur euro euros ref reference motif libelle janvier fevrier mars avril mai
juin juillet aout septembre octobre novembre decembre janv fevr fev juil sept oct nov dec pour par de du des le
la les et en au aux a sur inst instantane recu emis permanent europeen faveur ordre objet date
""".split())

PARTICLES = frozenset(["de", "du", "d", "des", "van", "von", "der", "den", "le", "la", "ben", "bin", "ibn",
                       "el", "al", "dos", "da", "di", "del", "della", "mac", "mc", "st", "ste", "saint", "sainte"])

# Institutions and well known brands: kept, they help the analysis and are not personal data.
KNOWN_ORGS = frozenset(fold(w) for w in """
urssaf|dgfip|dgfp|impots|impots.gouv|tresor public|cpam|caf|msa|pole emploi|france travail|ameli|insee|inpi|
infogreffe|bpi|bpifrance|carsat|agirc|arrco|agirc-arrco|apec|opco|cnil|banque de france|la poste|sncf|ratp|
edf|engie|totalenergies|total|orange|sfr|bouygues|bouygues telecom|free|free mobile|amazon|google|apple|
microsoft|ovh|ovhcloud|pennylane|qonto|shine|stripe|paypal|sumup|bnp|bnp paribas|societe generale|
credit agricole|lcl|cic|caisse d'epargne|banque populaire|credit mutuel|boursorama|hsbc|axa|allianz|maif|macif|
matmut|groupama|generali|carrefour|auchan|leclerc|e.leclerc|lidl|aldi|intermarche|casino|monoprix|franprix|
metro|ikea|leroy merlin|castorama|darty|fnac|boulanger|decathlon|uber|ubereats|deliveroo|air france|
easyjet|airbnb|booking|indeed|linkedin|facebook|meta|adobe|canva|notion|slack|zoom|dropbox|openai|anthropic
""".replace("\n", "").split("|"))

LEGAL_FORMS = r"(?:SASU|SAS|SARL|EURL|SA|SCI|SNC|SCP|SELARL|SELAS|SELAFA|SCM|SCOP|GIE|EIRL|SCEA|EARL|GAEC)"

ORG_LEAD_TRIM = frozenset(fold(w) for w in """
facture factures client clients fournisseur fournisseurs prlv vir virement sepa cb chez de du des pour le la les
ref objet societe entreprise cabinet et a au aux par avec l d
""".split())

VOIES = (r"rue|avenue|av|boulevard|bd|blvd|impasse|imp|allee|allée|chemin|che|place|pl|route|rte|quai|passage|"
         r"esplanade|cours|villa|square|residence|résidence|lotissement|lieu-dit|lieu dit|hameau|faubourg|fbg|"
         r"rond-point|rond point|parvis|promenade|sentier|voie|cite|cité|domaine|chaussee|chaussée|mail|montee|montée")

MONTHS = (r"janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre|"
          r"janv\.?|f[ée]vr?\.?|avr\.?|juil\.?|sept\.?|oct\.?|nov\.?|d[ée]c\.?")

UP = "A-ZÀ-ÖØ-Ý"
LOW = "a-zß-öø-ÿ"
LETTER = UP + LOW
NAME_WORD = rf"[{UP}][{LETTER}'’\-]*"

# ---------------------------------------------------------------- regexes

RE_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![\w-])")
RE_URL = re.compile(r"(?<![\w@])(?:https?://|www\.)[^\s<>\"')\]]+", re.I)
RE_IP = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])")
RE_IBAN = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}(?![A-Za-z0-9])")
RE_IBAN_CTX = re.compile(r"\b(?:iban|rib)\b", re.I)
RE_NIR = re.compile(r"(?<![\d])[12][\s.]?\d{2}[\s.]?\d{2}[\s.]?(?:\d{2}|2[ABab])[\s.]?\d{3}[\s.]?\d{3}(?:[\s.]?\d{2})?(?![\d])")
RE_CARD = re.compile(r"(?<![\d])(?:\d[ \-]?){12,18}\d(?![\d])")
RE_SIRET = re.compile(r"(?<![\d])\d{3}[\s.]?\d{3}[\s.]?\d{3}[\s.]?\d{5}(?![\d])")
RE_SIREN = re.compile(r"(?<![\d,.])\d{3}[\s.]?\d{3}[\s.]?\d{3}(?![\d]|[,.]\d)")
RE_SIREN_CTX = re.compile(r"\b(?:siren|siret|rcs|immatricul\w*|n°\s*entreprise)\b", re.I)
RE_MONEY_AFTER = re.compile(r"^\s?(?:€|eur\b|euros?\b|k€|m€|ht\b|ttc\b)", re.I)
RE_TVA = re.compile(r"(?<![A-Z0-9])FR[\s]?[0-9A-HJ-NP-Z]{2}[\s]?\d{3}[\s]?\d{3}[\s]?\d{3}(?![\d])")
RE_TVA_EU = re.compile(r"(?<![A-Z0-9])(?:BE|DE|IT|ES|NL|LU|PT|AT|PL|IE|DK|SE|FI|EL|CZ|HU|RO|BG|HR|SK|SI|EE|LV|LT|CY|MT)"
                       r"[\s]?[0-9A-Z]{8,12}(?![A-Z0-9])")
RE_TVA_CTX = re.compile(r"\b(?:tva|vat|intracom\w*)\b", re.I)
RE_TEL_FR = re.compile(r"(?<![\w+])(?:(?:\+|00)33[\s.\-]?(?:\(0\)[\s.\-]?)?|0)[1-9](?:[\s.\-]?\d{2}){4}(?![\d])")
RE_TEL_INTL = re.compile(r"(?<![\w+])\+(?!33)\d{1,3}(?:[\s.\-]?\(?\d{1,4}\)?){2,5}(?![\d])")
RE_DATE = re.compile(rf"(?<![\d])(?:\d{{1,2}}[/.\-]\d{{1,2}}[/.\-](?:\d{{4}}|\d{{2}})|\d{{4}}-\d{{2}}-\d{{2}}|"
                     rf"\d{{1,2}}(?:er)?\s+(?:{MONTHS})\s+\d{{4}})(?![\d])", re.I)
RE_BIRTH_CTX = re.compile(r"(?:n[ée]e?(?:\(e\))?\s+le|date\s+de\s+naissance|naissance|ddn|birth\s*date|date\s+of\s+birth)"
                          r"\s*[:\-]?\s*$", re.I)
RE_MATRICULE = re.compile(r"(?i:\bmatricule|\bmat\.|\bn°\s*salari[ée])\s*[:\-]?\s*(?P<v>[A-Z0-9][A-Z0-9\-]{1,14})\b")
RE_ADDRESS = re.compile(
    rf"(?<![\w])\d{{1,4}}(?:\s?(?:bis|ter|quater|[a-dA-D])\b)?,?\s+(?i:{VOIES})\.?\s+"
    rf"[{LETTER}'’\- ]{{2,60}}")
ADDRESS_TAIL_TRIM = frozenset(["email", "mail", "e-mail", "tel", "tél", "telephone", "téléphone", "iban", "siret",
                               "siren", "n", "no", "cedex", "bp", "cs", "fax", "port", "portable", "mobile"])
RE_CP_VILLE = re.compile(
    rf"(?<![\w])(?:F-)?(?:0[1-9]|[1-8]\d|9[0-8])\d{{3}}\s+(?=[{UP}])[{LETTER}'’\-]+"
    rf"(?:[\s\-](?:[{UP}][{LETTER}'’\-]*|sur|sous|en|le|la|les|de|du|des|lès|lez|aux|au|et))*"
    rf"(?:\s+CEDEX(?:\s+\d{{1,2}})?)?")
CP_STOP = frozenset(fold(w) for w in "total montant euros eur ht ttc net brut solde page tva".split())

CIVILITY = (r"M\.|Mr\.?|MR|Mme\.?|MME|Mlle|MLLE|Monsieur|MONSIEUR|Madame|MADAME|Mademoiselle|MADEMOISELLE|"
            r"Me|Maître|MAITRE|MAÎTRE|Dr\.?|DR|Docteur|DOCTEUR|Pr\.?")
RE_CIVILITY = re.compile(rf"(?<![\w.])(?:{CIVILITY})\s+(?=[{UP}])")
RE_BANK_PREFIX = re.compile(
    r"(?<![\w])(?:VIR(?:EMENT)?S?|PRLV|PRELEVEMENT|PRÉLÈVEMENT|VIRT)"
    r"(?:\s+(?:SEPA|INST(?:ANTANE)?|RECU|REÇU|EMIS|ÉMIS|PERMANENT|EUROPEEN|EUROPÉEN|DE|DU|DES|EN\s+FAVEUR\s+DE|"
    r"POUR|A|À|FAVEUR|ORDRE|RECU\s+DE|EMIS\s+VERS|VERS|/FRM|FRM|DE:))*\s+", re.I)
RE_WORD = re.compile(rf"[{LETTER}][{LETTER}'’\-]*")
RE_ORG_SUFFIX = re.compile(rf"(?<![\w])((?:[{UP}0-9][\w&'’.\-]*\s+){{1,4}}){LEGAL_FORMS}(?![\w])")
RE_ORG_PREFIX = re.compile(rf"(?<![\w]){LEGAL_FORMS}\s+((?:[{UP}0-9][\w&'’.\-]*)(?:\s+[{UP}0-9&][\w&'’.\-]*){{0,3}})")


def is_upper_word(w: str) -> bool:
    letters = [c for c in w if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def is_title_word(w: str) -> bool:
    return w[:1].isupper() and not is_upper_word(w)


def mostly_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.6


# ---------------------------------------------------------------- detectors

def _ctx_before(text: str, start: int, rx: re.Pattern, width: int = 40) -> bool:
    return bool(rx.search(text[max(0, start - width):start]))


def detect_patterns(text: str, mask_dates: bool = False) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    add = spans.append

    for m in RE_EMAIL.finditer(text):
        add((m.start(), m.end(), "EMAIL"))
    for m in RE_URL.finditer(text):
        add((m.start(), m.end(), "URL"))
    for m in RE_IP.finditer(text):
        add((m.start(), m.end(), "IP"))

    for m in RE_IBAN.finditer(text):
        s = m.group()
        ctx = _ctx_before(text, m.start(), RE_IBAN_CTX, 25)
        # shrink from the right until the checksum holds (the regex can swallow a following word)
        end = len(s)
        found = None
        while end >= 15:
            cand = s[:end].rstrip()
            if iban_ok(cand):
                found = cand
                break
            end -= 1
        if found:
            add((m.start(), m.start() + len(found), "IBAN"))
        elif ctx:
            add((m.start(), m.end(), "IBAN"))

    for m in RE_NIR.finditer(text):
        if nir_ok(m.group()):
            add((m.start(), m.end(), "NIR"))

    for m in RE_CARD.finditer(text):
        d = digits(m.group())
        if len(d) in (15, 16, 19) and luhn_ok(d) and not nir_ok(m.group()):
            add((m.start(), m.end(), "CARTE"))

    for m in RE_SIRET.finditer(text):
        d = digits(m.group())
        if luhn_ok(d) or _ctx_before(text, m.start(), RE_SIREN_CTX):
            add((m.start(), m.end(), "SIRET"))

    for m in RE_SIREN.finditer(text):
        d = digits(m.group())
        ctx = _ctx_before(text, m.start(), RE_SIREN_CTX)
        money = bool(RE_MONEY_AFTER.match(text[m.end():m.end() + 6]))
        if ctx or (luhn_ok(d) and not money):
            add((m.start(), m.end(), "SIREN"))

    for m in RE_TVA.finditer(text):
        add((m.start(), m.end(), "TVA"))
    for m in RE_TVA_EU.finditer(text):
        if _ctx_before(text, m.start(), RE_TVA_CTX, 30):
            add((m.start(), m.end(), "TVA"))

    for m in RE_TEL_FR.finditer(text):
        add((m.start(), m.end(), "TEL"))
    for m in RE_TEL_INTL.finditer(text):
        if 8 <= len(digits(m.group())) <= 15:
            add((m.start(), m.end(), "TEL"))

    for m in RE_DATE.finditer(text):
        if RE_BIRTH_CTX.search(text[max(0, m.start() - 30):m.start()]):
            add((m.start(), m.end(), "DATE_NAISSANCE"))
        elif mask_dates:
            add((m.start(), m.end(), "DATE"))

    for m in RE_MATRICULE.finditer(text):
        add((m.start("v"), m.end("v"), "MATRICULE"))

    for m in RE_ADDRESS.finditer(text):
        s = m.group()
        words = s.rstrip().split(" ")
        while len(words) > 3 and fold(words[-1]) in ADDRESS_TAIL_TRIM | {""}:
            words.pop()
        add((m.start(), m.start() + len(" ".join(words)), "ADRESSE"))

    for m in RE_CP_VILLE.finditer(text):
        city = m.group().split(None, 1)[1] if " " in m.group() else ""
        first = fold(city.split()[0]) if city.split() else ""
        if first in CP_STOP:
            continue
        add((m.start(), m.end(), "CP_VILLE"))

    return spans


def _name_run(text: str, pos: int, max_words: int = 4, stop: frozenset = NAME_STOP):
    """Collect name-like words from pos: capitalised or uppercase words, or particles, on one line."""
    words = []
    i = pos
    while len(words) < max_words:
        m = RE_WORD.match(text, i)
        if not m:
            break
        w = m.group()
        f = fold(w)
        if f in stop or not (w[:1].isupper() or f in PARTICLES):
            break
        words.append((m.start(), m.end(), w))
        sp = re.match(r"[ \t]+", text[m.end():])
        if not sp:
            break
        i = m.end() + sp.end()
    while words and fold(words[-1][2]) in PARTICLES:
        words.pop()
    return (words[-1][1] if words else pos), words


def _known_org(surface: str) -> bool:
    f = fold(surface)
    return f in KNOWN_ORGS or any(f.startswith(k + " ") for k in KNOWN_ORGS)


def detect_names(text: str) -> list[tuple[int, int, str]]:
    """Person names from civilities, first names and bank counterparties."""
    spans = []
    fn = first_names()

    for m in RE_CIVILITY.finditer(text):
        end, words = _name_run(text, m.end())
        if words:
            spans.append((words[0][0], end, "PERSONNE"))

    for m in RE_BANK_PREFIX.finditer(text):
        if RE_CIVILITY.match(text, m.end()):
            continue  # handled by the civility rule
        end, words = _name_run(text, m.end(), 4, BANK_STOP)
        if not words:
            continue
        surface = text[words[0][0]:end]
        if len(surface) < 3 or _known_org(surface):
            continue
        if len(words) >= 2 and any(fold(w[2]) in fn for w in words):
            spans.append((words[0][0], end, "PERSONNE"))
        else:
            spans.append((words[0][0], end, "TIERS"))

    for m in RE_WORD.finditer(text):
        w = m.group()
        f = fold(w)
        if len(f) < 3 or f not in fn or not w[:1].isupper():
            continue
        right_end, right = m.end(), []
        nxt = re.match(r"[ \t]+", text[m.end():])
        if nxt:
            right_end, right = _name_run(text, m.end() + nxt.end(), 3)
        start = m.start()
        left = re.search(rf"([{UP}][{UP}'’\-]+)[ \t]+$", text[max(0, m.start() - 40):m.start()])
        if left and fold(left.group(1)) not in NAME_STOP and not _known_org(left.group(1)):
            start = m.start() - len(left.group(0))
        n_words = 1 + len(right) + (1 if start < m.start() else 0)
        if n_words == 1 and (f in AMBIGUOUS_FIRST_NAMES or is_upper_word(w)):
            continue  # a lone first name that is also a common word, or an isolated uppercase word
        spans.append((start, right_end if right else m.end(), "PERSONNE"))
    return spans


def detect_orgs(text: str) -> list[tuple[int, int, str]]:
    spans = []
    for m in RE_ORG_SUFFIX.finditer(text):
        words = list(RE_WORD.finditer(m.group(1)))
        start = m.start(1)
        for w in words:
            if fold(w.group()) in ORG_LEAD_TRIM:
                start = m.start(1) + w.end()
                while start < m.end() and text[start] in " \t":
                    start += 1
            else:
                break
        name = text[start:m.start(1) + len(m.group(1).rstrip())]
        if name and fold(name) not in KNOWN_ORGS:
            spans.append((start, m.end(), "SOCIETE"))
    for m in RE_ORG_PREFIX.finditer(text):
        name = m.group(1)
        if fold(name) not in KNOWN_ORGS:
            spans.append((m.start(), m.end(), "SOCIETE"))
    return spans
