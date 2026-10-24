# Vérification des documentations officielles des sources

Consultation : **2026-10-24**, depuis l'environnement de développement (proxy
sortant). Méthode : téléchargement des documents officiels, extraits exacts,
aucune donnée complétée de mémoire. Statuts : **VÉRIFIÉ**, **PARTIEL**,
**NON VÉRIFIÉ**. Règle du projet : aucun connecteur n'est codé sur un point
non vérifié.

## Synthèse

| Source | Statut | Implémentation |
|---|---|---|
| Dumps DILA LEGI | VÉRIFIÉ (réserves sur la sémantique des dates) | ✅ connecteur `dila-legi-xml/0.1.0` |
| API Légifrance (PISTE) | PARTIEL | ⏳ après compte PISTE (DEC-05) |
| Judilibre | VÉRIFIÉ (CGU et quotas non vérifiés) | ⏳ ING-05 |
| Open data justice administrative | VÉRIFIÉ | ⏳ ING-06 |
| EUR-Lex / CELLAR | PARTIEL | ⏳ ING-07 |
| Textes réglementaires (COJ, CJA, loi 71-1130, RGPD, règlement IA) | VÉRIFIÉ / PARTIEL — voir `docs/compliance/dependances-reglementaires.md` | — |

Sites inaccessibles le 2026-10-24 : `piste.gouv.fr` (503), `legifrance.gouv.fr`
(403), `eur-lex.europa.eu` (challenge anti-robot), page CGU de la Cour de
cassation (JavaScript requis). Les points qui en dépendent restent **NON VÉRIFIÉS**.

## 1. Dumps DILA LEGI — VÉRIFIÉ

* Serveur : `https://echanges.dila.gouv.fr/OPENDATA/LEGI/` — stock
  `Freemium_legi_global_20250713-140000.tar.gz` (1,1 Go) puis deltas
  `LEGI_AAAAMMJJ-HHMMSS.tar.gz` quotidiens (parfois plusieurs par jour).
* Fiche DILA LEGI (24/08/2017) : « Les données sont réutilisables
  gratuitement sous licence ouverte v2.0. Les réutilisateurs s'obligent à
  mentionner : la paternité des données (DILA) ; l'URL d'accès longue de
  téléchargement ; le nom du fichier téléchargé ainsi que la date du
  fichier. » ; mise à jour « au plus tard dans les 3 jours ouvrés après
  publication au JORF » ; obligation d'utiliser le dernier stock pour une
  première intégration.
* Divergence : data.gouv.fr indique la licence `fr-lo` (Licence Ouverte v1)
  pour le même jeu — à lever (validation juridique).
* Documentation XML Légifrance (v1.2.2, 18/10/2018, archive
  `DTD_LEGIFRANCE_20181017.7z`) : corrections par « annule et remplace » ;
  application des livraisons « dans l'ordre croissant » ; la suppression
  « peut aussi indiquer un changement d'état de vigueur à non vigueur pour
  LEGI (la donnée est supprimée dans la branche vigueur et recréée dans la
  branche non vigueur) » ; « id » = version, « cid » = identifiant commun aux
  versions ; DTD non versionnées, **pas de XSD**.
* DTD `legi_article.dtd` : `META_ARTICLE (NUM, ETAT, DATE_DEBUT, DATE_FIN, TYPE)` ;
  valeurs d'ETAT : ABROGE, ABROGE_DIFF, ANNULE, DISJOINT, MODIFIE,
  MODIFIE_MORT_NE, PERIME, TRANSFERE, VIGUEUR, VIGUEUR_DIFF ; `DATE_FIN
  @example 2999-01-01`.
* Avertissement DILA : la réutilisation « ne peut avoir pour objet ou pour
  effet de réidentifier les personnes concernées ».
* Vérifié sur l'archive réelle `LEGI_20261023-215041.tar.gz` (SHA-256
  `edf0a051…fad0ef`) : structure des fichiers article, bloc VERSIONS, LIENS,
  NOTA, liste de suppression (chemins sans extension).

**Non vérifié** (impact : ADR 0002, risque R-03) : définition officielle de
chaque ETAT ; sémantique de `2999-01-01` (« sans fin ») et caractère
inclusif/exclusif de DATE_FIN — déduits des données ; autres sentinelles
observées (`2999-12-31` dans la DTD des sections, `2222-02-22` dans des
attributs `fin`).

Conséquences appliquées dans le code : chemin source inclus dans la
connaissance enregistrée ; retrait appliqué au seul chemin exact ; attribution
(source, URL, archive horodatée) portée par chaque `SourceReference`.

## 2. API Légifrance (PISTE) — PARTIEL

* Fiche officielle data.gouv.fr (dataservice « Légifrance ») : accès
  restreint, inscription sur `https://piste.gouv.fr/registration`, « quota /
  jeton », données soumises à la Licence Ouverte 2.0, aux CGU PISTE et de
  l'API Légifrance.
* Swagger public (copie api.gouv.fr, v1.6.2.5, 61 chemins) : `POST
  /consult/getArticle`, `/consult/legiPart` (texte LEGI à une date),
  `/consult/getArticleByCid`, `/search` (`fond` ∈ JORF, CNIL, CETAT, JURI,
  CONSTIT, KALI, CODE_DATE, CODE_ETAT, LODA_DATE, LODA_ETAT, ALL, CIRC, ACCO ;
  `pageSize` max 100), `/list/code`, `/chrono/*`, `/suggest`…
* Constat : le `basePath` publié (`/dila/legifrance-beta/lf-engine-app`)
  renvoie 404, alors que `/dila/legifrance/lf-engine-app/consult/ping`
  existe (challenge Bearer) en sandbox et en production → Swagger probablement
  périmé.
* **Non vérifié** : CGU PISTE et Légifrance, quotas chiffrés, Swagger courant,
  support documenté du flux `client_credentials`.

## 3. Judilibre — VÉRIFIÉ (CGU et quotas non vérifiés)

* Dépôt officiel `Cour-de-cassation/judilibre-search` (commit `f8aa7db3`,
  2026-10-21) : OpenAPI 3.0.2 « JUDILIBRE-public » v1.2.5.
* Environnements : `https://sandbox-api.piste.gouv.fr/cassation/judilibre/v1.0`,
  `https://api.piste.gouv.fr/cassation/judilibre/v1.0` ; en-tête `KeyId`.
* Endpoints `GET` : `/search` (50 résultats/page, 10 000 au total, sans texte
  intégral), `/decision?id=`, `/export` (lots ≤ 1000), `/scan`
  (`search_after`), `/taxonomy`, `/stats`, `/transactionalhistory`
  (synchronisation), `/healthcheck`. Zonage : `introduction`, `expose`,
  `moyens`, `motivations`, `dispositif`, `annexes` (`start` inclus, `end` exclu).
* Données « enrichies et pseudonymisées » ; Licence Ouverte 2.0 + CGU PISTE
  + CGU de réutilisation de la Cour de cassation.
* **Non vérifié** : texte des CGU de la Cour de cassation, quotas.

## 4. Justice administrative — VÉRIFIÉ

* `https://opendata.justice-administrative.fr/` : Conseil d'État (depuis le
  30/09/2021), CAA (31/03/2022), TA (30/06/2022) ; archives zip mensuelles
  par juridiction (`/DCE/2026/10/CE_202610.zip`…) contenant des XML ;
  fichiers `*_documents_reverses.csv` (Latin-1).
* CGU (18/01/2022) : « Le site de données ouvertes … ne comporte pas
  d'API » ; Licence Ouverte 2.0 + CGU ; mentions obligatoires (numéro,
  juridiction, formation, siège, date ; date de dernière mise à jour) ;
  signalement sans délai des défauts de pseudonymisation ; interdiction de
  réutilisation des données d'identité des magistrats et membres du greffe à
  des fins de profilage (art. L. 10 CJA).
* Balises XML documentées (`Numero_ECLI`, `Date_Lecture`, `Code_Publication`,
  `Texte_Integral`…) ; **pas de XSD** publié.

## 5. EUR-Lex / CELLAR — PARTIEL

* SPARQL CELLAR `https://publications.europa.eu/webapi/rdf/sparql` (Virtuoso,
  testé) ; négociation de contenu REST
  `https://publications.europa.eu/resource/celex/{CELEX}` (testée sur 4 actes,
  versions consolidées `0AAAA…-AAAAMMJJ`).
* Décision 2011/833/UE : réutilisation gratuite, à des fins commerciales ou
  non, sous conditions (citer la source, ne pas altérer le sens).
* **Non vérifié** : service web EUR-Lex et ses conditions d'inscription,
  avis juridique et licence actuelle d'EUR-Lex, quotas CELLAR.

## 6. Textes réglementaires

Consultés via le stock DILA LEGI du 2025-07-13 (COJ L111-13, CJA L10,
loi 71-1130 art. 54–55) et via CELLAR (RGPD art. 22, 28, 35 ; règlement
(UE) 2024/1689 consolidé au 27.07.2026 et règlement modificatif (UE)
2026/1744). Extraits et réserves dans le document de conformité. Réserve
principale : les textes français reflètent l'état du 2025-07-13 ; les deltas
postérieurs n'ont pas été rejoués.
