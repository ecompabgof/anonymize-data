---
description: Crée en local une copie pseudonymisée d'un fichier ou d'un dossier client, à utiliser à la place de l'original
argument-hint: <fichier ou dossier>
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/anonymiser:*)
---
Lance exactement cette commande, seule, sans rien y ajouter :

`${CLAUDE_PLUGIN_ROOT}/bin/anonymiser $ARGUMENTS`

Ensuite, donne à l'utilisateur les chemins des copies produites, le décompte des remplacements et les éventuelles erreurs.
Ne lis jamais le fichier original. Travaille seulement sur les copies du dossier anonymise/.
Rappelle à l'utilisateur de relire la copie : la détection n'est pas parfaite.
