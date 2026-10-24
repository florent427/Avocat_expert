# Modèle de données initial

Source de vérité : `services/api/migrations/*.sql` (appliquées par
`avx migrate`, empreintes contrôlées). PostgreSQL 16, extensions `pgcrypto`,
`unaccent`, `vector`.

## Corpus juridique (public, sans tenant) — `0001`, `0004`

| Table | Rôle | Points clés |
|---|---|---|
| `legal_source` | source (DILA_LEGI…) | mode d'accès, URL, licence et obligations |
| `ingestion_run` | lot d'ingestion | version du connecteur, archive, SHA-256, statistiques, statut |
| `legal_document` | texte (code, loi…) | identifiant officiel (`LEGITEXT…`), nature, titre, `territorial_scope` (NULL = non renseigné) |
| `provision` | disposition logique | (document, type, numéro) |
| `provision_version` | **version citable** | identifiant officiel (`LEGIARTI…`), statut brut, `[valid_from, valid_to)` + `valid_period`, valeurs brutes, texte + SHA-256, NOTA, chemin et empreinte du fichier source, lot, `sys_from/sys_to`, `superseded_by`, retrait, `tsv`, `embedding` |
| `provision_version_declared` | versions annoncées par la source (bloc VERSIONS) | détection des lacunes de couverture |
| `legal_reference` | références croisées (bloc LIENS) | type (CITATION, MODIFIE…), sens, cible |
| `source_withdrawal` | entrées de la liste de suppression | `matched` ; jamais de DELETE |
| `court_decision` | décisions (structure initiale) | ECLI, juridiction, date, texte pseudonymisé ; **aucun champ d'identité de magistrat ou de greffier** (art. L111-13 COJ, L10 CJA) |
| `case_law_relation` | relations de jurisprudence | origine : source / extraction automatique / validation humaine |
| `corpus_lexeme_stats`, `corpus_stats` | vues matérialisées BM25 | rafraîchies après ingestion |

Invariants (triggers `avx_forbid_history_rewrite`) : pas de DELETE ; contenu
non modifiable ; ligne close non modifiable ; une seule ligne courante par
identifiant officiel (index unique partiel).

Requête type « droit applicable au 1er juin 2020 » :
```sql
SELECT * FROM provision_version
WHERE valid_period @> DATE '2020-06-01' AND sys_to IS NULL AND NOT withdrawn_from_source;
```
Requête type « ce que le système savait le 1er mars 2027 » : remplacer
`sys_to IS NULL` par `sys_from <= t AND (sys_to IS NULL OR sys_to > t)`.

## Organisations, utilisateurs, dossiers — `0002`

`organization` (sous-traitants autorisés, durée de conservation),
`app_user` (issuer + subject OIDC, MFA requis), `membership` (rôle),
`matter` (date d'appréciation, territoire), `matter_document` (clé S3,
SHA-256, type, taille, statut d'analyse antivirale, numéro de pièce,
effacement), `matter_fact` (FAIT / ÉVÉNEMENT / HYPOTHÈSE, précision de date,
pièce et localisation source, établi ou non), `legal_argument` (favorable /
contraire, validation humaine), `report`, `report_claim` (nature de
l'affirmation, statut FONDÉE / INCERTAINE / BLOQUÉE), `citation_check`
(résultat lexverif, versions du moteur et du contrat).

RLS FORCE sur toutes ces tables ; `avx_resolve_principal()` pour
l'authentification.

## Traces, coûts, accès, facturation — `0003`

`execution_trace` / `execution_step` (empreintes, routage, statuts, durées),
`usage_record` (fournisseur, modèle, jetons entrants/sortants/cache, appels,
durée, coût estimé en micro-euros, version de la table de prix, tenant),
`tenant_budget` (plafond souple/dur, mode dégradé), `billing_account`,
`access_log` (insertion seule).

## Évolutions prévues
* Textes (versions de `LEGITEXT`), sections (`LEGISCTA`) et structure (phase C).
* Champ territorial qualifié (tables de correspondance territoires ↔ dispositions, avec origine et validation).
* Partitionnement de `provision_version` et `execution_step` à volumétrie réelle.
* HMAC par tenant pour les empreintes de données client (SEC-06).
