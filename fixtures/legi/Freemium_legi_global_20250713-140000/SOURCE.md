# Provenance des fixtures LEGI (stock)

| | |
|---|---|
| Producteur | Direction de l'information légale et administrative (DILA) |
| URL de téléchargement | https://echanges.dila.gouv.fr/OPENDATA/LEGI/Freemium_legi_global_20250713-140000.tar.gz |
| Nom et date du fichier | `Freemium_legi_global_20250713-140000.tar.gz` — stock du 2025-07-13 |
| SHA-256 de l'archive | `f862b4a2238e11ec3c48ec70f3b1c68bac0bb1985907841666b98608653d4eca` |
| Téléchargée le | 2026-10-24 |
| Licence | Licence Ouverte v2.0 (fiche DILA LEGI du 24/08/2017) |

Fichiers copiés sans modification, chemins d'origine conservés. Ils illustrent
les cas rencontrés lors de l'analyse du stock complet par les parseurs
(2 276 109 fichiers XML) et absents des livraisons incrémentales :

* article sans état ni date (`ETAT` vide, `DATE_DEBUT` et `DATE_FIN` à
  2999-01-01 ; 229 644 cas) : `LEGIARTI000006850356` ;
* deux articles distincts non numérotés (`NUM` vide ; 25 121 cas) d'un même
  arrêté : `LEGIARTI000029825776`, `LEGIARTI000029825777` ;
* texte en abrogation différée à la date `2222-01-01` (variante de la date non
  fixée) : version et structure de `LEGITEXT000018840114` ;
* section dont le contexte ne porte pas de `cid` (4 cas) : `LEGISCTA000006090465` ;
* fichier d'index ELI (`eli/…/versions.xml` ; 280 936 fichiers), non ingéré.

Données publiques ; aucune donnée personnelle ni donnée client.
