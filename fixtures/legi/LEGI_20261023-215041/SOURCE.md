# Provenance des fixtures LEGI

| | |
|---|---|
| Producteur | Direction de l'information légale et administrative (DILA) |
| Base | LEGI (codes, lois et règlements consolidés) |
| URL de téléchargement | https://echanges.dila.gouv.fr/OPENDATA/LEGI/LEGI_20261023-215041.tar.gz |
| Nom et date du fichier | `LEGI_20261023-215041.tar.gz` — extraction DILA du 2026-10-23 21:50:41 (archive incrémentale) |
| SHA-256 de l'archive | `edf0a051ba3ae4d2f38d256772927a77f6ce3365b40ff35710a9bb5443fad0ef` |
| Téléchargée le | 2026-10-24 |
| Licence | Licence Ouverte v2.0 (fiche DILA LEGI du 24/08/2017) |

Les fichiers sont copiés **sans modification** depuis l'archive, chemins
d'origine conservés (à partir de `legi/`). Sélection : 40 versions d'articles

* Code du travail : L5411-1, L5421-4, L5422-1, L5422-2, L5427-1 (toutes les versions livrées) ;
* Code des assurances : L125-2 (6 versions, 1985 → en vigueur) ;
* Code des impositions sur les biens et services : L161-1 (dont `ABROGE_DIFF` et `VIGUEUR_DIFF` 2027) ;
* Code de l'énergie : D251-1, **sélection partielle volontaire** de 5 versions sur 22 (dont versions
  `MODIFIE_MORT_NE` et version de durée nulle), pour tester la détection de lacunes de couverture.

`liste_suppression_legi.dat` contient les **3 premières lignes** du fichier
réel de la même archive (les articles visés ne font pas partie de la sélection).

Ces textes sont des données publiques ; aucune donnée personnelle ni donnée
client ne figure dans les fixtures.
