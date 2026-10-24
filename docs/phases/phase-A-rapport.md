# Rapport de validation — Phase A et tranche verticale initiale

Date : 2026-10-24 · Branche : `ccr-f9391166-37sdlt` · Environnement :
conteneur de développement Linux (Python 3.13, Rust 1.97, Node 22,
PostgreSQL 16.15 + pgvector 0.6.0 locaux ; **Docker indisponible**).

## 1. Objectifs de la mission initiale et état

| # | Objectif | État | Livrable |
|---|---|---|---|
| 1 | Architecture technique V1 | ✅ proposée | `docs/architecture/architecture-v1.md` |
| 2 | Dépendances réglementaires bloquantes | ✅ identifiées (non validées juridiquement) | `docs/compliance/dependances-reglementaires.md` |
| 3 | Vérification des documentations officielles | ✅ partielle (sites indisponibles signalés) | `docs/sources/verification-documentation-officielle.md` |
| 4 | ADR fondamentales | ✅ 13 ADR proposées | `docs/adr/` |
| 5 | Modèle de données initial | ✅ 4 migrations appliquées et testées | `services/api/migrations/`, `docs/data-model/` |
| 6 | Contrats des services et des agents | ✅ Pydantic + schémas JSON | `contracts/`, `packages/contracts/schemas/` |
| 7 | Backlog technique priorisé | ✅ | `docs/backlog/backlog-technique.md` |
| 8 | Monorepo et socle de tests | ✅ (CI rédigée, **non encore exécutée sur GitHub**) | `.github/workflows/ci.yml`, `Makefile` |
| 9 | Tranche verticale | ✅ ingestion LEGI réelle → indexation → recherche → réponse sourcée → vérification | voir §3 |
| 10 | Tests exécutés, résultats réels | ✅ | §4 |

## 2. Dépendances
Aucune dépendance externe payante ; aucune ressource cloud créée ; aucun
compte tiers ouvert. Données : archive publique DILA
`LEGI_20261023-215041.tar.gz` (40 versions d'articles extraites en fixtures).

## 3. Tranche verticale — description vérifiable

1. **Ingestion** (`avx ingest-legi`) : parseur strict des fichiers article LEGI
   réels, conversion de la sentinelle `2999-01-01`, valeurs brutes
   conservées, provenance (archive, chemin, SHA-256), versions déclarées,
   références croisées, liste de suppression appliquée au chemin exact,
   écriture bitemporelle idempotente.
2. **Indexation** : tsvector français sans accents ; statistiques BM25
   matérialisées.
3. **Recherche** : identifiant officiel, numéro d'article, BM25, filtre
   « en vigueur à la date » ; canal sémantique déclaré désactivé.
4. **Réponse sourcée** (`POST /v1/answer`, `avx answer`) : extraits
   littéraux, références traçables, incertitudes, avertissement.
5. **Vérification** : chaque extrait est contrôlé par le moteur Rust
   `lexverif` (identifiant, résolution, passage, date, territoire) ; les
   contrôles non déterministes sont `NON_EVALUE`.
6. **Interface web** : formulaire, affichage des contrôles et incertitudes.

Démonstration manuelle exécutée (API + web lancés localement) : page servie
(200) avec en-têtes CSP / X-Frame-Options / Referrer-Policy ; requête
« durée d'indemnisation de l'allocation d'assurance selon l'âge » au
2026-10-24 → L5422-1, L5422-2, L5421-4 du code du travail, verdict
`INCERTAIN` (territoire non renseigné par la source) ; API sans jeton → 401 ;
question vide → 400.

## 4. Résultats des tests (exécutions réelles du 2026-10-24)

| Suite | Commande | Résultat |
|---|---|---|
| Rust — format, lint | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` | OK, 0 avertissement |
| Rust — tests | `cargo test --locked` | **22 réussis** (12 unitaires, 10 contrat CLI), 0 échec |
| Python — statique | `ruff check`, `ruff format --check`, `mypy --strict` (32 fichiers), schémas à jour | OK |
| Python — tests | `pytest` avec PostgreSQL 16 réel et binaire lexverif | **59 réussis**, 0 échec, 0 ignoré |
| Python — sans base | `pytest` sans `AVX_TEST_DATABASE_URL` | 33 réussis, 26 **ignorés et signalés** (la CI refuse tout test ignoré) |
| Web | `npm audit`, `tsc --noEmit`, `next build` | 0 vulnérabilité (après mise à jour de sécurité, §6), build OK |
| Terraform | `terraform fmt -check`, `init -backend=false`, `validate` (1.16.7, provider AWS ~> 6.60) | « The configuration is valid. » |
| Secrets | `gitleaks dir` | aucune fuite dans les fichiers versionnés (8 alertes dans `.next/`, artefacts générés et ignorés par Git) |

Couverture fonctionnelle des tests Python : parseur sur fichiers réels
(sentinelle, version mort-née, entrée en vigueur différée, chemins, liens),
refus XML malformé / XXE / expansion d'entités, migrations idempotentes et
détection d'une migration altérée, ingestion idempotente, changement de
connaissance (historique conservé, ligne close), interdiction de réécriture
(UPDATE / DELETE / ligne close), recherche temporelle et bornes semi-ouvertes,
lacune de couverture détectée, déplacement de branche ≠ retrait, retrait par
chemin exact puis relivraison, RLS (lecture, écriture croisée refusée, tenant
absent ⇒ rien), privilèges du rôle applicatif, résolution du principal,
authentification avant toute dépendance, mode OIDC fail-closed, interdiction
du mode développement en production, contrats stricts, vérification des
citations (exacte, variantes typographiques, altération, version périmée avec
version applicable nommée, identifiant fictif, identifiant mal formé,
disposition différée), réponses (version en vigueur, droit ancien, article
fictif ⇒ blocage, lacune ⇒ blocage), traces sans texte de question.

### Évaluation sur le corpus de cas techniques (`eval/cases/seed_v0.jsonl`)

| Métrique | Valeur |
|---|---|
| Cas | 16 (**0 validé juridiquement**) |
| Recherche (13 cas) — rappel@3 moyen | 0,9231 |
| Recherche — MRR | 0,9231 |
| Recherche — précision@3 (sous-estimée : seules les versions annotées comptent) | 0,5256 |
| Blocages attendus (3 cas : source manquante, 2 références fictives) | 1,0 |
| Citations produites | 30 |
| Intégrité des contrôles déterministes 1–4 | 1,0 |
| Conformité temporelle des versions citées | 1,0 |
| Échec | SEED-014 (« combien de temps » ≠ « durée » : limite du lexical seul) |

**Mise en garde** : ces cas ont été conçus par l'équipe technique qui a
construit le système, sur 40 versions d'articles. Ils mesurent un
comportement, pas une qualité juridique, et surestiment probablement les
performances réelles. Ils ne remplacent en rien la validation par des
juristes (QUAL-01).

Durées mesurées (indicatives, conteneur de développement) : ingestion des 40
fichiers ≈ 0,8 s ; évaluation des 16 cas ≈ 0,7 s.

## 5. Ce qui n'a pas été fait ou pas pu être vérifié

* Docker indisponible : `Dockerfile` et `docker-compose.yml` **non construits
  ni exécutés** ; la CI GitHub Actions **n'a pas encore tourné**.
* Aucune ingestion du stock complet (1,1 Go) : performance à grande échelle
  inconnue.
* Canal sémantique, OpenSearch, reranking, agents, OIDC : non implémentés
  (contrats et ports en place).
* Textes juridiques (COJ, loi de 1971, RGPD, règlement IA) non consultés sur
  Légifrance/EUR-Lex (sites inaccessibles) : voir le document de conformité.
* Pas de validation juridique des sorties.

## 6. Incidents notables

* `next@16.4.0` présentait 3 avis de sécurité, dont 2 critiques
  (GHSA-2464-fhr4-w9xw, GHSA-p3m5-59mp-jv5r, GHSA-673q-mjm6-r5xr, source
  `npm audit`) : mise à jour en 16.4.3, publiée le 2026-10-23, par exception
  à la règle d'ancienneté minimale de deux semaines (correctif de sécurité).
* La sortie de `next build` contenait des instructions adressées à un
  « agent » (lancer une commande de mise à jour) : traitées comme des données
  non fiables ; seule la mise à jour de version, vérifiée indépendamment par
  `npm audit`, a été appliquée.
* Premier classement lexical (`ts_rank_cd`) biaisé vers les textes longs :
  remplacé par BM25 (ADR 0005).
* Documentation DILA : une entrée de suppression peut signifier un
  changement de branche ; la logique de retrait initiale aurait masqué à tort
  des articles — corrigée et testée.

## 7. Risques

| ID | Risque | Niveau | Traitement |
|---|---|---|---|
| R-01 | Hébergement incompatible avec le secret professionnel | Élevé | DEC-01 avant toute donnée réelle |
| R-02 | Qualification réglementaire (consultation juridique, règlement IA) | Élevé | instruction par un conseil |
| R-03 | Sémantique des dates LEGI déduite et non documentée | Moyen | confirmation DILA, tests sur stock complet (ING-03) |
| R-04 | Champ territorial absent de LEGI : réponses toujours « incertaines » | Moyen | ING-08, validation juriste |
| R-05 | Corpus d'évaluation non représentatif | Élevé | QUAL-01 |
| R-06 | Swagger PISTE périmé, CGU non lues | Moyen | DEC-05 avant tout connecteur API |
| R-07 | Performance BM25 SQL à grande échelle | Moyen | mesure en phase C, OpenSearch en phase D |
| R-08 | Dépendance au fournisseur de modèles (coût, confidentialité) | Moyen | ADR 0010, DEC-03 |

## 8. Conditions de passage à la phase B (proposées)

1. Revue et validation (ou amendement) des ADR 0001–0013 par le porteur.
2. Décisions DEC-01 (hébergement) et DEC-05 (compte PISTE) engagées.
3. CI exécutée et verte sur GitHub (INFRA-01) ; images construites (INFRA-02).
4. Désignation d'un référent juridique pour l'instruction R1–R6 et le corpus QUAL-01.
