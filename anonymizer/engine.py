"""Pseudonymisation engine: detect, give each value a stable token, replace.

The same person, company or number gets the same token everywhere in a run
([PERSONNE_1], [SOCIETE_2], [IBAN_1]...), across all the files of that run,
so the result can still be analysed (who paid what, how many lines per tiers).
"""
from __future__ import annotations

import re
from collections import Counter

from . import rules as R

NAME_KINDS = ("PERSONNE", "SOCIETE", "TIERS")
CONTAINERS = ("SOCIETE", "TIERS", "ADRESSE")
STRICT_KINDS = ("EMAIL", "IBAN", "NIR", "CARTE", "TEL")
RE_TOKEN = re.compile(r"\[[A-Z_]+_\d+\]")
CIVILITY_WORDS = frozenset(R.fold(w) for w in
                           "m mr mme mlle monsieur madame mademoiselle me maitre dr docteur pr".split())
LEGAL_WORDS = frozenset(R.fold(w) for w in R.LEGAL_FORMS.strip("(?:)").split("|"))


class EngineError(Exception):
    """An error whose message is safe to show (it never contains document content)."""


_NLP = None


def load_ner():
    global _NLP
    if _NLP is None:
        try:
            import spacy
        except ImportError as e:
            raise EngineError("spaCy n'est pas installé : lance install.sh") from e
        try:
            _NLP = spacy.load("fr_core_news_md", disable=["parser", "lemmatizer", "morphologizer",
                                                          "attribute_ruler"])
        except OSError as e:
            raise EngineError("modèle spaCy fr_core_news_md absent : lance install.sh") from e
        _NLP.max_length = 2_000_000
    return _NLP


def _title_same_length(text: str) -> str | None:
    t = text.title()
    return t if len(t) == len(text) else None


def _clean_name_span(text: str, start: int, end: int, kind: str) -> tuple[int, int] | None:
    """Trim a NER span to its name words; None if nothing name-like is left."""
    seg = text[start:end]
    if "\n" in seg:
        seg = seg.split("\n", 1)[0]
        end = start + len(seg)
    words = list(R.RE_WORD.finditer(seg))
    if not words or any(ch.isdigit() for ch in seg):
        return None
    if kind == "PERSONNE":  # the name starts after the last civility (« Relancer M. Vasseur » -> « Vasseur »)
        civ = [i for i, w in enumerate(words) if R.fold(w.group()) in CIVILITY_WORDS]
        if civ and civ[-1] < len(words) - 1:
            words = words[civ[-1] + 1:]
    stop = R.NAME_STOP | CIVILITY_WORDS | (R.ORG_LEAD_TRIM if kind == "SOCIETE" else frozenset())
    while words and (R.fold(words[0].group()) in stop or R.fold(words[0].group()) in R.PARTICLES):
        words.pop(0)
    trail = R.NAME_STOP if kind == "PERSONNE" else R.NAME_STOP - LEGAL_WORDS
    while words and (R.fold(words[-1].group()) in trail or R.fold(words[-1].group()) in R.PARTICLES):
        words.pop()
    if not words:
        return None
    s, e = start + words[0].start(), start + words[-1].end()
    surface = text[s:e]
    if len(surface) < 3 or len(words) > 5 or R._known_org(surface):
        return None
    if not any(w.group()[:1].isupper() for w in words):
        return None
    return s, e


def _merge_same_kind(spans):
    out = []
    for s in sorted(spans):
        if out and out[-1][2] == s[2] and s[0] < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], s[1]), s[2])
        else:
            out.append(s)
    return out


def resolve(spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Keep non-overlapping spans: same-kind overlaps merge, then higher priority wins."""
    by_kind = {}
    for s in spans:
        by_kind.setdefault(s[2], []).append(s)
    merged = [m for k in by_kind for m in _merge_same_kind(by_kind[k])]
    containers = [s for s in merged if s[2] in CONTAINERS]
    merged = [s for s in merged
              if not (s[2] == "PERSONNE" and any(c[0] <= s[0] and s[1] <= c[1] and c[1] - c[0] > s[1] - s[0]
                                                 for c in containers))]
    merged.sort(key=lambda s: (R.RANK[s[2]], -(s[1] - s[0]), s[0]))
    kept = []
    for s in merged:
        if all(s[1] <= k[0] or s[0] >= k[1] for k in kept):
            kept.append(s)
    return sorted(kept)


class Pseudonymizer:
    def __init__(self, keep_orgs: bool = False, mask_dates: bool = False, use_ner: bool = True):
        self.keep_orgs = keep_orgs
        self.mask_dates = mask_dates
        self.nlp = load_ner() if use_ner else None
        self.tokens: dict[tuple[str, tuple], str] = {}
        self.issued = Counter()
        self.found = Counter()
        self.parts: dict[str, str] = {}
        self.forms: dict[str, str] = {}
        self._sweep_rx = None

    # ------------------------------------------------------------ tokens

    @staticmethod
    def key(kind: str, surface: str) -> tuple:
        if kind in ("IBAN", "TVA"):
            return (re.sub(r"\s", "", surface).upper(),)
        if kind in ("NIR", "CARTE", "SIRET", "SIREN", "TEL"):
            d = R.digits(surface)
            if kind == "TEL" and d.startswith("33") and len(d) == 11:
                d = "0" + d[2:]
            return (d,)
        if kind == "EMAIL":
            return (surface.lower(),)
        words = [R.fold(w) for w in R.RE_WORD.findall(surface)]
        if kind == "PERSONNE":
            words = [w for w in words if w not in CIVILITY_WORDS and w not in R.PARTICLES]
            return tuple(sorted(words)) or (R.fold(surface),)
        if kind in ("SOCIETE", "TIERS"):
            words = [w for w in words if w not in LEGAL_WORDS]
            return tuple(words) or (R.fold(surface),)
        return (R.fold(surface),)

    def token_for(self, kind: str, surface: str) -> str:
        k = self.key(kind, surface)
        if kind == "PERSONNE" and len(k) == 1 and k[0] in self.parts:
            return self.parts[k[0]]
        t = self.tokens.get((kind, k))
        if t is None:
            self.issued[kind] += 1
            t = f"[{kind}_{self.issued[kind]}]"
            self.tokens[(kind, k)] = t
            if kind in NAME_KINDS:
                self._add_parts(kind, surface, t)
        return t

    def _add_parts(self, kind: str, surface: str, token: str):
        fn = R.first_names()
        words = R.RE_WORD.findall(surface)
        multi = len(words) > 1
        for w in words:
            f = R.fold(w)
            if (len(f) < 3 or f in R.NAME_STOP or f in R.PARTICLES or f in CIVILITY_WORDS or f in LEGAL_WORDS
                    or (multi and f in fn)):
                continue
            if f not in self.parts or (kind == "PERSONNE" and not self.parts[f].startswith("[PERSONNE")):
                self.parts[f] = token
                for v in {w, w.title(), w.upper(), f.title(), f.upper()}:
                    self.forms[v] = token
                self._sweep_rx = None

    # ------------------------------------------------------------ detection

    def _ner_spans(self, texts: list[str]) -> list[list[tuple[int, int, str]]]:
        out: list[list[tuple[int, int, str]]] = [[] for _ in texts]
        if self.nlp is None:
            return out
        jobs = []  # (index, offset, text)
        for i, t in enumerate(texts):
            if not t or len(t.strip()) < 3:
                continue
            for off, line_block in _blocks(t):
                jobs.append((i, off, line_block, False))
                if R.mostly_upper(line_block):
                    tt = _title_same_length(line_block)
                    if tt:
                        jobs.append((i, off, tt, True))
        uniq = {}
        for j in jobs:
            uniq.setdefault(j[2], None)
        docs = dict(zip(uniq, self.nlp.pipe(list(uniq), batch_size=64)))
        for i, off, block, _ in jobs:
            src = texts[i]
            for ent in docs[block].ents:
                if ent.label_ == "PER":
                    kind = "PERSONNE"
                elif ent.label_ == "ORG" and not self.keep_orgs:
                    kind = "SOCIETE"
                else:
                    continue
                c = _clean_name_span(src, off + ent.start_char, off + ent.end_char, kind)
                if c:
                    out[i].append((c[0], c[1], kind))
        return out

    def detect_many(self, texts: list[str]) -> list[list[tuple[int, int, str]]]:
        ner = self._ner_spans(texts)
        result = []
        for t, extra in zip(texts, ner):
            if not t:
                result.append([])
                continue
            spans = R.detect_patterns(t, self.mask_dates) + R.detect_names(t) + extra
            if not self.keep_orgs:
                # bank counterparties that are not people are companies: merge them with the company spans
                spans = [(s, e, "SOCIETE" if k == "TIERS" else k) for s, e, k in spans] + R.detect_orgs(t)
            result.append(resolve(spans))
        return result

    # ------------------------------------------------------------ rendering

    def _sweep(self, text: str) -> str:
        if not self.forms:
            return text
        if self._sweep_rx is None:
            alts = sorted(self.forms, key=len, reverse=True)
            self._sweep_map = self.forms
            self._sweep_rx = re.compile(r"(?<![\w'’\-\[])(" + "|".join(map(re.escape, alts)) + r")(?![\w'’\-\]])")

        def rep(m):
            self.found["balayage"] += 1
            return self._sweep_map[m.group(1)]
        parts = RE_TOKEN.split(text)
        toks = RE_TOKEN.findall(text)
        out = []
        for i, p in enumerate(parts):
            out.append(self._sweep_rx.sub(rep, p))
            if i < len(toks):
                out.append(toks[i])
        return "".join(out)

    def _render(self, text: str, spans) -> str:
        out = []
        last = 0
        for s, e, kind in spans:
            out.append(text[last:s])
            out.append(self.token_for(kind, text[s:e]))
            self.found[kind] += 1
            last = e
        out.append(text[last:])
        return "".join(out)

    def _final_check(self, text: str) -> str:
        """Defence in depth: any strict identifier still visible is masked and counted."""
        spans = [s for s in R.detect_patterns(text) if s[2] in STRICT_KINDS]
        spans = [s for s in spans if not RE_TOKEN.search(text[s[0]:s[1]])]
        if not spans:
            return text
        self.found["rattrapés"] += len(spans)
        return self._render(text, resolve(spans))

    def process(self, texts: list[str], presets: list[tuple[str, str]] = ()) -> list[str]:
        """Pseudonymise texts that belong together (one run). presets: (value, kind) known from table columns."""
        all_spans = self.detect_many(texts)
        regs = [(t[s:e], k) for t, spans in zip(texts, all_spans) for s, e, k in spans if k in NAME_KINDS]
        regs += [(v, k) for v, k in presets if k in NAME_KINDS]
        regs.sort(key=lambda x: (x[1] != "PERSONNE", -len(R.RE_WORD.findall(x[0]))))
        for surface, kind in regs:
            self.token_for(kind, surface)
        for v, k in presets:
            if k not in NAME_KINDS:
                self.token_for(k, v)
        out = []
        for t, spans in zip(texts, all_spans):
            if not t:
                out.append(t)
                continue
            r = self._render(t, spans)
            r = self._sweep(r)
            out.append(self._final_check(r))
        return out

    def process_one(self, text: str) -> str:
        return self.process([text])[0]

    def report(self) -> dict:
        return {k: v for k, v in sorted(self.found.items())}


def _blocks(text: str, size: int = 100_000):
    """Split long texts on line breaks into blocks for the NER, with their offsets."""
    if len(text) <= size:
        yield 0, text
        return
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start:
                end = nl + 1
        yield start, text[start:end]
        start = end
