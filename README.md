# anonymize-data

Plugin Claude Code pour travailler sur des documents clients sans les envoyer en clair.

1. Il bloque tout message qui cite un document client original (`@releve.pdf`) avant qu'il parte, et crée à la place une copie pseudonymisée, en local.
2. Il interdit à Claude d'ouvrir les originaux (lecture, recherche, commandes du terminal).
3. Claude travaille sur la copie, où chaque personne, société ou numéro est remplacé par un repère stable : `[PERSONNE_1]`, `[SOCIETE_2]`, `[IBAN_1]`.

Le même client garde le même repère dans tous les fichiers traités ensemble. Claude peut donc encore compter, regrouper, rapprocher.

## Ce qui a été vérifié

Essai du 26/11/2026 avec Claude Code 2.1.319, sur un relevé fictif contenant un nom et un IBAN témoins.

| Essai | Sans le plugin | Avec le plugin |
|---|---|---|
| Message avec `@clients/releve.csv` | Claude recopie le nom et l'IBAN | Message bloqué avant l'envoi, copie créée |
| Lecture du fichier par Claude (outil Read), mode sans permission | Lu | Refusé |
| `cat clients/releve.csv` par Claude, mode sans permission | Lu | Refusé |
| « Donne le total et dis qui a payé », mode sans permission | | Lecture refusée, Claude anonymise, calcule sur la copie, le nom reste masqué |
| `/anonymize-data:anonymiser clients/`, mode par défaut | | Copie créée, aucun nom ni IBAN témoin dedans |
| Installation publique dans une configuration neuve et isolée, sur Mac : `curl` du moteur, puis plugin depuis la marketplace GitHub, puis message avec `@clients/releve.csv` | | Moteur et plugin 3.0.0 installés, message bloqué, copie créée, aucun témoin |

Et 38 tests automatiques, dont tous les cas qui fuyaient dans la version 2 de ce plugin (noms en majuscules dans les libellés bancaires, sociétés, SIREN, téléphone, numéro de sécu saisi comme un nombre, cellules courtes).

## Installation

Testé sur Mac. Linux est prévu mais pas encore testé. Python 3.9 ou plus récent.

1. Le moteur local (spaCy et les lecteurs de fichiers, dans `~/.anonymize-data`) :

```bash
curl -fsSL https://raw.githubusercontent.com/ecompabgof/anonymize-data/main/install.sh | bash
```

Pour lire aussi les PDF scannés et les photos, ajoute l'OCR (Tesseract, par Homebrew ou apt) :

```bash
curl -fsSL https://raw.githubusercontent.com/ecompabgof/anonymize-data/main/install.sh | bash -s -- --ocr
```

2. Le plugin, dans Claude Code :

```
/plugin marketplace add ecompabgof/anonymize-data
/plugin install anonymize-data@anonymize-data
```

Active-le seulement dans les projets qui contiennent des documents clients : il bloque la lecture de tous les PDF, images, fichiers Office et CSV qui ne sont pas des copies produites par lui.

### Si tu avais la version 2

La v2 s'installait à la main dans `~/.claude/plugins/anonymize-data`, avec son propre environnement Python. Supprime ce dossier, puis suis les deux étapes ci-dessus :

```bash
rm -rf ~/.claude/plugins/anonymize-data
```

Refais avec `/anonymize-data:anonymiser` les copies produites par la v2 : elle laissait passer des noms et des numéros.

## Utilisation

Cite un document comme d'habitude :

```
@clients/releve_novembre.pdf justifie les virements
```

Le message est bloqué. La copie `anonymise/releve_novembre.anon.md` est créée, et Claude Code affiche le message à renvoyer, avec la copie à la place de l'original. Relis la copie, puis renvoie.

Pour tout un dossier :

```
/anonymize-data:anonymiser clients/
```

Ou demande simplement à Claude de travailler sur un fichier : la garde lui refuse l'original et lui indique la commande `anonymiser`.

Options de la commande :

| Option | Effet |
|---|---|
| `--sortie DOSSIER` | dossier des copies (par défaut `anonymise/`) |
| `--garder-societes` | laisse visibles les noms de sociétés (les personnes restent masquées) |
| `--masquer-dates` | masque aussi les dates ordinaires (gardées par défaut, sauf les dates de naissance) |

## Formats

| Format | Copie produite |
|---|---|
| PDF avec texte, PDF scanné (OCR) | Markdown, page par page |
| Photos (JPG, PNG, HEIC, WEBP, TIFF) | Markdown (OCR) |
| Word .docx | Markdown : texte, tableaux, en-têtes, pieds de page, notes, commentaires |
| PowerPoint .pptx | Markdown : diapositives, tableaux, notes, commentaires |
| Excel .xlsx | Excel, mêmes feuilles et colonnes |
| CSV et TSV (séparateur `;` reconnu) | même format |
| Texte, Markdown | Markdown |

Les métadonnées (auteur, historique, commentaires masqués d'Excel) ne sont pas recopiées.
Les formats .xls, .ods, .doc, .odt, .rtf, .ppt, .eml et .msg sont bloqués mais pas encore lus : enregistre-les en .xlsx, .docx, .pptx ou PDF.

## Ce qui est masqué

Personnes (civilité, prénoms connus, noms en majuscules, colonnes « Nom », « Salarié »...), sociétés (forme juridique, colonnes « Client », « Fournisseur », contreparties des virements), e-mails, téléphones, IBAN (clé vérifiée), cartes bancaires (clé vérifiée), numéros de sécurité sociale, SIREN et SIRET (clé vérifiée, ou mot « SIREN » à côté), numéros de TVA, adresses, codes postaux avec ville, dates de naissance, matricules, liens, adresses IP.

Gardés : montants, dates ordinaires, institutions et grandes marques (URSSAF, impôts, banques, EDF, Orange, Amazon...), utiles pour l'analyse.

Un nom repéré une fois est masqué partout ailleurs dans les fichiers traités ensemble, même écrit seul (« Dupont » dans une cellule courte).

## Limites, à connaître avant de s'en servir

- **C'est de la pseudonymisation, pas de l'anonymisation au sens du RGPD.** La copie garde les montants, les dates, les postes : avec d'autres informations, une personne peut être retrouvée. Pour le RGPD, ce sont encore des données personnelles. Le plugin réduit ce qui part, il ne dispense pas des règles du cabinet ni du contrat avec le fournisseur d'IA.
- **La détection n'est pas parfaite.** Relis la copie avant de l'envoyer. Les cas les plus faibles :
  - les noms écrits tout en minuscules (« rdv avec thomas bernard ») ;
  - un nom en majuscules dont le prénom n'est pas dans la liste et qui n'a pas de civilité ;
  - les textes mal lus par l'OCR.
- **La garde couvre les outils intégrés de Claude Code** (citation `@`, Read, Edit, Grep, et les commandes qui lisent un fichier). Elle ne couvre pas :
  - les fichiers texte et Markdown (.txt, .md) : ils ne sont pas bloqués, ne range pas de données clients dans ce format ;
  - les noms des fichiers et des dossiers, que Claude voit avec `ls`, Glob ou `find` : un nom comme `Bulletin_DUPONT_Jean.pdf` part en clair ;
  - les captures d'écran collées dans le message ;
  - les outils MCP (connecteurs) ;
  - un script qui ouvre lui-même les fichiers (`python analyse.py` sans le chemin dans la commande).
- Dans un dépôt git qui contient des CSV ou TSV originaux, `git diff`, `git show` et `git log -p` sont refusés, car ils afficheraient leur contenu. `git status`, `git add`, `git commit` et `git log` sans `-p` passent.
- Un dossier trop gros pour être vérifié à temps (plus de 5 000 fichiers ou 20 secondes) est refusé en entier, pour la recherche comme pour les commandes : vise un sous-dossier.
- Un message bloqué reste dans l'historique local de Claude Code, sur ton poste.
- La liste des prénoms (`anonymizer/data/first_names.txt`) est faite à la main : environ 550 prénoms courants en France. Ajoute ceux qui manquent.
- Testé seulement sur Mac. Linux n'est pas encore testé. Windows n'est pas pris en charge pour l'instant : pas d'installeur, rien de testé.

## Tests

```bash
python3 -m unittest tests.test_guard
~/.anonymize-data/venv/bin/python -m unittest discover -s tests -t .
```

Les tests de la garde n'ont besoin que de Python. Les tests du moteur utilisent des données fictives.

## Licence

MIT
