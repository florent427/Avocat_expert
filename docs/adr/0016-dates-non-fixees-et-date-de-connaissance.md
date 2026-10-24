# ADR 0016 — Dates non fixées par la source et date de connaissance du corpus

**Statut** : proposée — implémentée · 2026-10-24

## Contexte
La livraison LEGI du 2026-10-23 contient la valeur `2222-02-22` : en fin de
période d'articles `ABROGE_DIFF` (ex. art. 289 CGI, `LEGIARTI000048827413`,
dont la NOTA indique des dispositions « maintenues en vigueur jusqu'à leur
reprise par les mesures réglementaires »), en début de période d'éléments
`VIGUEUR_DIFF`, et dans `VERSIONS_A_VENIR`. La documentation XML DILA (2018)
ne définit pas cette valeur. Avant correction, elle était lue comme une date
réelle : l'article 289 était déclaré « en vigueur » avec certitude en 2030 et
la réponse affichait « jusqu'au 2222-02-22 ».

## Décision
* `2222-02-22` signifie « date non fixée » ; `2999-01-01` et au-delà
  « absence de date ». Interprétation **déduite des données** (NOTA
  concordantes), à confirmer auprès de la DILA (ING-03). Valeurs brutes
  toujours conservées.
* Modèle : `valid_from` facultatif (début non fixé : jamais en vigueur à une
  date connue), `end_undetermined` (fin non fixée).
* **Date de connaissance** : date de la dernière livraison intégrée
  (`avx_knowledge_date`, d'après l'horodatage du nom d'archive). L'état d'une
  version à date non fixée n'est connu que jusqu'à cette date ; au-delà, il
  est `INDETERMINE` et la citation est au mieux `INCERTAIN`, jamais
  `CONFORME`. Toute question à une date postérieure à la date de connaissance
  reçoit une incertitude explicite.
* Contrat du moteur `lexverif` porté en **v2** (`valid_from` facultatif,
  `end_undetermined`, `knowledge_date`, résolution `INDETERMINEE`) ; le
  contrat v1 est refusé.

## Conséquences
* Les lignes déjà ingérées ne sont pas réécrites : une relivraison produit
  une nouvelle version (historique immuable).
* `SourceReference` expose `end_undetermined` ; les types web sont régénérés.
