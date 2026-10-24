# ADR 0003 — Ingestion LEGI par dumps open data DILA avant l'API PISTE

**Statut** : proposée — implémentée · 2026-10-24

## Contexte
Deux accès officiels existent : les dumps XML (`echanges.dila.gouv.fr/OPENDATA/LEGI/`,
stock « Freemium » + deltas quotidiens, DTD publiée) et l'API Légifrance sur
PISTE (inscription, quotas, CGU). Le portail PISTE était indisponible (503)
le 2026-10-24 ; la copie publique du Swagger (v1.6.2.5, 2024) annonce un
`basePath` qui renvoie 404 : il est probablement périmé.

## Décision
* Source de référence du corpus : **dumps DILA** (format vérifié sur archive
  réelle et sur la DTD officielle). Application des deltas dans l'ordre
  croissant des horodatages, conformément à la documentation DILA.
* L'API PISTE sera utilisée en complément (fraîcheur, consultation unitaire)
  **après** obtention d'identifiants et vérification du Swagger servi par
  PISTE ; aucun endpoint n'est codé avant.
* Ingestion obligatoire du dernier stock Freemium avant toute première
  diffusion (exigence de la fiche DILA).

## Conséquences
+ Pas de dépendance à des quotas pour l'ingestion de masse ; reproductibilité
  (archives horodatées, empreintes).
− Latence de mise à jour (≤ 3 jours ouvrés selon la fiche DILA) ; stock de 1,1 Go
  à traiter (ingestion par flux, backlog ING-02).
