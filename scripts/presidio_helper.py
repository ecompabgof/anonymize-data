"""Shared Presidio engine + FR-specific custom recognizers."""
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

_analyzer = None
_anonymizer = None

ENTITIES = [
    'PERSON', 'EMAIL_ADDRESS', 'PHONE_NUMBER_FR', 'IBAN_CODE',
    'LOCATION', 'FR_NIR', 'CREDIT_CARD', 'DATE_TIME', 'URL', 'IP_ADDRESS',
    'FR_SIRET', 'FR_SIREN', 'FR_TVA', 'FR_ADDRESS', 'FR_POSTAL_CITY',
    'FR_MATRICULE', 'FR_JOB_TITLE', 'FR_CIVILITY',
    'US_SSN', 'NRP',
]

OPERATORS = {
    'PERSON': OperatorConfig('replace', {'new_value': '[NOM]'}),
    'EMAIL_ADDRESS': OperatorConfig('replace', {'new_value': '[EMAIL]'}),
    'PHONE_NUMBER': OperatorConfig('replace', {'new_value': '[TEL]'}),
    'PHONE_NUMBER_FR': OperatorConfig('replace', {'new_value': '[TEL]'}),
    'IBAN_CODE': OperatorConfig('replace', {'new_value': '[IBAN]'}),
    'LOCATION': OperatorConfig('replace', {'new_value': '[ADRESSE]'}),
    'FR_NIR': OperatorConfig('replace', {'new_value': '[NIR]'}),
    'CREDIT_CARD': OperatorConfig('replace', {'new_value': '[CB]'}),
    'DATE_TIME': OperatorConfig('replace', {'new_value': '[DATE]'}),
    'URL': OperatorConfig('replace', {'new_value': '[URL]'}),
    'IP_ADDRESS': OperatorConfig('replace', {'new_value': '[IP]'}),
    'FR_SIRET': OperatorConfig('replace', {'new_value': '[SIRET]'}),
    'FR_SIREN': OperatorConfig('replace', {'new_value': '[SIREN]'}),
    'FR_TVA': OperatorConfig('replace', {'new_value': '[TVA]'}),
    'FR_ADDRESS': OperatorConfig('replace', {'new_value': '[ADRESSE]'}),
    'FR_POSTAL_CITY': OperatorConfig('replace', {'new_value': '[CP_VILLE]'}),
    'FR_MATRICULE': OperatorConfig('replace', {'new_value': '[MATRICULE]'}),
    'FR_JOB_TITLE': OperatorConfig('replace', {'new_value': '[POSTE]'}),
    'FR_CIVILITY': OperatorConfig('replace', {'new_value': '[CIVILITE]'}),
    'US_SSN': OperatorConfig('replace', {'new_value': '[SSN]'}),
    'NRP': OperatorConfig('replace', {'new_value': '[NATIONALITE]'}),
}


def _french_recognizers():
    """Custom French recognizers — covers entities Presidio default misses."""
    recognizers = []

    # SIRET (14 chiffres, espaces tolérés)
    recognizers.append(PatternRecognizer(
        supported_entity='FR_SIRET',
        supported_language='fr',
        patterns=[Pattern(name='siret', regex=r'\b\d{3}[\s.]?\d{3}[\s.]?\d{3}[\s.]?\d{5}\b', score=0.85)],
        context=['siret', 'établissement']
    ))

    # SIREN (9 chiffres avec contexte)
    recognizers.append(PatternRecognizer(
        supported_entity='FR_SIREN',
        supported_language='fr',
        patterns=[Pattern(name='siren', regex=r'\b\d{3}[\s.]?\d{3}[\s.]?\d{3}\b', score=0.5)],
        context=['siren', 'rcs', 'entreprise']
    ))

    # TVA intra UE
    recognizers.append(PatternRecognizer(
        supported_entity='FR_TVA',
        supported_language='fr',
        patterns=[Pattern(name='tva', regex=r'\b(?:FR|BE|DE|IT|ES|NL|LU|PT|AT|PL|IE|DK|SE|FI|GR|CZ|HU|RO|BG|HR|SK|SI|EE|LV|LT|CY|MT)[\s]?\d{2,12}\b', score=0.9)],
        context=['tva', 'vat']
    ))

    # NIR FR (sécu sociale) — boost score haut pour battre LOCATION model
    recognizers.append(PatternRecognizer(
        supported_entity='FR_NIR',
        supported_language='fr',
        patterns=[
            # Strict 15-digit format with key
            Pattern(name='nir_strict', regex=r'\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2])\s?(?:0[1-9]|[1-8]\d|9[0-5]|2[ABab])\s?\d{3}\s?\d{3}\s?\d{2}\b', score=0.99),
            # Loose: 13 or 15 consecutive digits starting with 1 or 2
            Pattern(name='nir_15', regex=r'\b[12]\d{14}\b', score=0.95),
            Pattern(name='nir_13', regex=r'\b[12]\d{12}\b', score=0.85),
        ],
        context=['sécurité sociale', 'sécu', 'n°ss', 'n° ss', 'numéro ss', 'nir', 'social security', 'ss :']
    ))

    # Matricule — UNIQUEMENT après mot-clé matricule (strict lookbehind)
    recognizers.append(PatternRecognizer(
        supported_entity='FR_MATRICULE',
        supported_language='fr',
        patterns=[
            Pattern(name='matricule_explicit',
                    regex=r'(?i)(?:matricule|mat\.|n[°o]\s*matricule)\s*[:\-]?\s*([A-Z0-9]{3,12})\b',
                    score=0.95),
        ],
        context=['matricule']
    ))

    # Civilité + prénom + NOM — UNIQUEMENT avec préfixe explicite (Madame, M., Mme...)
    recognizers.append(PatternRecognizer(
        supported_entity='FR_CIVILITY',
        supported_language='fr',
        patterns=[
            Pattern(
                name='civility_name',
                regex=r'\b(?:Madame|Monsieur|Mme|M\.|Mlle|Mademoiselle)\s+[A-ZÀ-Ÿ][a-zà-ÿ\-]+(?:[\-\s][A-ZÀ-Ÿ][a-zà-ÿ\-]+)?\s+[A-ZÀ-Ÿ]{2,}(?:[\-\s][A-ZÀ-Ÿ]{2,})*\b',
                score=0.95
            ),
        ],
    ))

    # Postes FR — désactivé temporairement (trop FP)
    # Presidio PERSON s'occupe des noms.

    # Phone FR (mobile + fixe) — score haut pour éviter faux positifs
    recognizers.append(PatternRecognizer(
        supported_entity='PHONE_NUMBER_FR',
        supported_language='fr',
        patterns=[
            Pattern(name='tel_fr', regex=r'\b(?:\+33|0033|0)[1-9](?:[\s.\-]?\d{2}){4}\b', score=0.9),
        ],
        context=['téléphone', 'tel', 'tél', 'mobile', 'portable', 'phone']
    ))

    # Adresse FR (numéro + voie + ...)
    recognizers.append(PatternRecognizer(
        supported_entity='FR_ADDRESS',
        supported_language='fr',
        patterns=[
            Pattern(name='fr_street', regex=r'\b\d{1,4}\s+(?:bis|ter)?\s*(?:rue|avenue|av\.?|boulevard|bd|impasse|allée|chemin|place|route|quai|passage|esplanade|cours|villa|square|rond[\-\s]?point|parvis)\s+[^\n,;]{2,80}', score=0.9),
        ],
    ))

    # Code postal + ville FR (5 chiffres + 1-4 mots capitalisés)
    recognizers.append(PatternRecognizer(
        supported_entity='FR_POSTAL_CITY',
        supported_language='fr',
        patterns=[
            Pattern(name='fr_cp_city', regex=r'\b\d{5}\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ\-\']+(?:[\s\-][A-ZÀ-Ÿa-zà-ÿ\-\']+){0,3}\b', score=0.9),
        ],
    ))

    return recognizers


def _build_analyzer():
    """Build bilingual fr+en analyzer with custom FR recognizers."""
    try:
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "fr", "model_name": "fr_core_news_md"},
                {"lang_code": "en", "model_name": "en_core_web_sm"},
            ],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()
        analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=['fr', 'en'])
    except Exception:
        try:
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "fr", "model_name": "fr_core_news_md"}],
            }
            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()
            analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=['fr'])
        except Exception:
            analyzer = AnalyzerEngine()

    # Register custom FR recognizers
    for rec in _french_recognizers():
        try:
            analyzer.registry.add_recognizer(rec)
        except Exception:
            pass

    return analyzer


def get_engines():
    global _analyzer, _anonymizer
    if _analyzer is None:
        _analyzer = _build_analyzer()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


def _detect_language(text):
    if not text:
        return 'fr'
    fr_markers = sum(1 for w in ['le ', 'la ', 'les ', 'de ', 'du ', 'des ', 'est ', 'à ',
                                   'avec ', 'pour ', 'dans ', 'sur ', 'une ', 'un ',
                                   'salaire', 'cotisation', 'urssaf', 'siret'] if w in text.lower())
    return 'fr' if fr_markers >= 2 else 'en'


# Common FR words Presidio LOCATION/PERSON wrongly matches — deny list
FR_DENY_LIST = {
    'bureau', 'bureaux', 'études', 'techniques', 'salaire', 'brut', 'net',
    'coefficient', 'ancienneté', 'position', 'statut', 'matricule', 'siret',
    'cotisation', 'cotisations', 'sécurité', 'sociale', 'urssaf', 'msa',
    'famille', 'maladie', 'retraite', 'décès', 'invalidité', 'incapacité',
    'tranche', 'plafonnée', 'déplafonnée', 'mensuel', 'annuel', 'titres',
    'restaurant', 'forfait', 'télétravail', 'navigo', 'congés', 'rtt',
    'feb', 'jan', 'fév', 'avr', 'jui', 'aoû', 'sep', 'oct', 'nov', 'déc',
    'mat.', 'inval.', 'page', 'unit', 'price', 'total', 'amount',
    'description', 'subtotal', 'receipt', 'invoice', 'paid', 'bill',
    'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'company', 'tax', 'vat',
}


def _filter_false_positives(results, text):
    """Drop low-confidence LOCATION/PERSON matches on common FR words."""
    filtered = []
    for r in results:
        if r.entity_type in ('LOCATION', 'PERSON', 'NRP'):
            matched = text[r.start:r.end].strip().lower()
            # Skip deny-list matches
            if matched in FR_DENY_LIST or len(matched) <= 3:
                continue
            # Skip purely numeric matches (LOCATION sometimes catches NIR/SIRET)
            digits_only = matched.replace(' ', '').replace('.', '').replace(',', '').replace('\n', '')
            if digits_only.isdigit():
                continue
            # Skip multi-line LOCATION/PERSON matches > 80 chars (likely span error)
            if r.entity_type == 'LOCATION' and ('\n' in matched or len(matched) > 80):
                continue
            # Skip if matched contains > 50% digits (mixed text/digits NIR-like)
            digit_count = sum(c.isdigit() for c in matched)
            if r.entity_type == 'LOCATION' and len(matched) > 5 and digit_count / len(matched) > 0.5:
                continue
        filtered.append(r)
    return filtered


def anonymize_text(text, language=None):
    """Run analyzer + anonymizer on text. Returns anonymized string."""
    if not text or not text.strip():
        return text
    analyzer, anonymizer = get_engines()
    lang = language or _detect_language(text)
    supported_langs = analyzer.supported_languages
    if lang not in supported_langs:
        lang = supported_langs[0]

    try:
        results = analyzer.analyze(text=text, language=lang, entities=ENTITIES)
    except Exception:
        results = analyzer.analyze(text=text, language=lang)

    results = _filter_false_positives(results, text)

    return anonymizer.anonymize(text=text, analyzer_results=results, operators=OPERATORS).text
