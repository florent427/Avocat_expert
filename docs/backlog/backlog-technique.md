# Backlog technique priorisé

P0 = bloquant pour la phase suivante · P1 = nécessaire avant bêta · P2 = après bêta.
« Validation » = action humaine (porteur, juriste, DPO, RSSI) requise.

## Décisions à prendre (porteur du projet)
| ID | Sujet | Prio | Dépend de |
|---|---|---|---|
| DEC-01 | ✅ 2026-10-24 : AWS en dev/recette sans données réelles ; **production à décider** (DPO, conseil) | P0 | DPO, conseil |
| DEC-02 | ✅ 2026-10-24 : Keycloak auto-hébergé | — | — |
| DEC-03 | Fournisseur(s) de modèles et conditions contractuelles (DPA, absence d'entraînement, localisation) | P0 phase E | DEC-01 |
| DEC-04 | Positionnement (outil réservé aux professionnels du droit) et CGU | P0 bêta | conseil |
| DEC-05 | ✅ 2026-10-24 : compte bac à sable PISTE créé par le porteur (en attente) | P0 phase C | porteur |

## Conformité
| ID | Tâche | Prio |
|---|---|---|
| COMP-01 | ✅ mention « système d'IA » affichée (web et API) ; reste : marquage lisible par machine des sorties générées (art. 50 §2) avant tout mode génératif | P0 phase E |
| COMP-02 | Registre de qualification du système au regard de l'annexe III (point 8) et de l'art. 6 §3, revu à chaque nouvel usage ou client | P0 bêta (validation) |
| COMP-03 | Identifier le texte remplaçant l'art. 66-2 de la loi 71-1130 au 01/02/2027 ; extraire les art. 56–66 | P1 |

## Phase B — socle
| ID | Tâche | Prio |
|---|---|---|
| INFRA-01 | ✅ CI verte sur la branche de travail ; **reste (porteur)** : protéger `main` (revue obligatoire, CI requise) dans les réglages GitHub | P0 |
| INFRA-02 | ✅ images construites, Trivy bloquant, SBOM CycloneDX, test de fumée en CI ; signature → INFRA-07 | — |
| INFRA-03 | ✅ modules complets, `validate` + checkov (0 échec, 31 exceptions motivées) ; **jamais appliqués** ; reste : compte AWS, état distant, image Keycloak optimisée | P0 |
| INFRA-04 | ✅ traces à liste blanche (ADR 0015) ; reste : métriques, collecteur | P1 |
| INFRA-05 | ✅ test pg_dump/pg_restore en CI (défaut de restauration trouvé et corrigé), PITR 14 j, procédure mensuelle | — |
| WEB-01 | ✅ ESLint (0 avertissement), Playwright mobile + ordinateur (6 tests) ; reste : tests de composants | P2 |
| WEB-03 | ✅ types générés depuis les schémas, vérifiés en CI | — |

| INFRA-06 | Sauvegarde logique hebdomadaire hors RDS (tâche ECS planifiée vers S3 chiffré) | P1 |
| INFRA-07 | Registre ECR du compte, recopie des images tierces, signature cosign et attestation de provenance, workflow de déploiement par OIDC GitHub → AWS (sans clé longue durée) | P0 avant recette |
| INFRA-08 | Image Keycloak optimisée (`kc.sh build`) construite et analysée en CI | P0 avant recette |
| INFRA-09 | Montées de version majeures planifiées (non proposées par Dependabot) : TypeScript 7 (nouveau compilateur, changement d'éditeur npm à vérifier), Node 26 (vérifier le statut LTS), `@types/node` aligné sur Node ; chacune avec notes de rupture lues et CI complète | P2 |
| SEC-10 | Rotation des secrets applicatifs (Secrets Manager) | P1 |
| SEC-11 | Chiffrement de bout en bout ALB → cibles | P2 |
| SEC-12 | Alertes de sécurité (GuardDuty, CloudTrail) via EventBridge vers l'astreinte | P1 |

## Phase C — corpus
| ID | Tâche | Prio |
|---|---|---|
| ING-01 | ✅ textes (`texte/version`), plan (`texte/struct`) et sections (`section_ta`) : parseurs vérifiés sur les DTD et par l'analyse du stock complet (2 276 109 fichiers : articles sans état ni date, non numérotés, sentinelle 2222-01-01, sections sans cid, index ELI), tables bitemporelles (0008, 0009), plan d'un texte à une date (`StructureRepository`) avec lacunes signalées ; reste : exposition par l'API (phase D) | — |
| ING-02 | ✅ lecture en flux du stock, lots transactionnels avec point de reprise, une ingestion à la fois par source, ordre des livraisons contrôlé, `avx sync-legi` (stock puis deltas postérieurs, hôte officiel seul) ; reste : planification en recette (tâche ECS) | — |
| ING-03 | Lecture exclusive de DATE_FIN retenue (décision déléguée du 24/10/2026) ; confirmation DILA et sentinelles 2999-12-31 / 2222-02-22 (2222-02-22 traité comme « date non fixée », ADR 0016) ; confirmer aussi le double classement en branches (copie la plus récente retenue) et les 11 328 retraits d'identifiants absents du corpus | P2 |
| ING-04 | JORF | P1 |
| ING-05 | Judilibre (spécification OpenAPI 1.2.5 vérifiée ; KeyId PISTE). **Critères d'acceptation R4** : requêtes visant un magistrat ou greffier refusées (tests), zone de composition non indexée, aucun filtre ni agrégat par juge | P1 |
| ING-06 | Justice administrative (archives zip XML mensuelles, CGU 18/01/2022). Mêmes critères R4 ; signalement des défauts de pseudonymisation | P1 |
| ING-07 | CELLAR/EUR-Lex (SPARQL + REST CELLAR vérifiés) | P1 |
| ING-08 | Qualification territoriale (outre-mer, Alsace-Moselle) avec validation juriste | P1 |
| ING-09 | Exploitation du graphe de références (résolution des cibles, transferts) ; blocs de liens stockés par empreinte (`legal_reference` : 23 M de lignes, 6,4 Go à 10,5 mois, chaque version reprenant son bloc) | P1 |
| ING-10 | ✅ `avx fraicheur-legi` : dernière livraison intégrée et publiée, livraisons en attente, retard en jours, code retour 3 si en retard ; reste : alarme CloudWatch en recette | — |
| ING-11 | Index ELI (`legi/global/eli/…/versions.xml`, 280 936 fichiers) : correspondances ELI → versions, pour citer et résoudre les identifiants ELI | P2 |

## Phase D — recherche et évaluation
| ID | Tâche | Prio |
|---|---|---|
| SRCH-01 | Adaptateur OpenSearch (analyseur français), comparaison avec BM25 PostgreSQL. **Mesure phase C** : BM25 SQL sur 1,8 M de versions = 17 s en médiane, 76 s au 95e centile ; questions en langage naturel sans réponse pertinente (4/4) — prérequis à toute recette utilisateurs | P0 |
| SRCH-02 | Sélection et évaluation d'un modèle d'embeddings ; activation pgvector (SEED-014) | P0 |
| SRCH-03 | Reranking (après mesure) | P1 |
| SRCH-04 | ✅ 2026-10-24 : texte nommé = périmètre (mots du titre exclus), verbes interrogatifs ignorés, seuil relatif BM25 0,5 ; **à recalibrer sur corpus annoté par des juristes** | P1 |
| QUAL-01 | Corpus ≥ 500 cas validés juridiquement (référent : porteur du projet, REF-01) | P0 (validation) |
| QUAL-02 | Interface de correction humaine des cas et des réponses | P0 |
| QUAL-03 | Métriques de couverture juridique par domaine | P1 |

## Phases E–F — agents et vérification
| ID | Tâche | Prio |
|---|---|---|
| AGT-01 | Orchestrateur typé + routage par complexité (ADR 0013) | P0 |
| AGT-02 | Ports `LanguageModel`/`Embedder`, comptabilité des coûts, quotas et plafonds | P0 |
| AGT-03 | Agents recherche législative, vérificateur indépendant, synthèse | P0 |
| AGT-04 | Isolation des contenus non fiables (injection de prompt), tests adversariaux | P0 |
| AGT-05 | Agents jurisprudence, contradiction, procédure (délais), chronologie | P1 |
| VER-01 | Vérificateur d'adéquation (contrôles 6–7) avec escalade humaine | P0 |

## Phases G–I — utilisateurs, documents, sécurité
| ID | Tâche | Prio |
|---|---|---|
| SEC-01 | OIDC + MFA + RBAC avec Keycloak (ADR 0011 amendée) | P0 |
| SEC-02 | Journal d'accès alimenté par toutes les routes | P0 |
| SEC-03 | Positionnement de `app.tenant_id` par transaction (`SET LOCAL`) et tests de pool | P0 |
| SEC-04 | Téléversement : liste blanche de types, taille, antivirus, stockage S3 chiffré, URL présignées courtes | P0 |
| SEC-05 | Contrôle des sorties réseau (egress) et protection SSRF des connecteurs | P0 |
| SEC-06 | HMAC par tenant pour les empreintes de données client | P1 |
| SEC-07 | Demandes RGPD (accès, effacement), politique de conservation, purge | P0 |
| SEC-09 | R3 : interdiction technique de réutiliser les données client pour les besoins propres de la plateforme (aucun export vers l'évaluation ou l'entraînement sans accord exprès du cabinet, contrôlé par test) | P0 |
| VAL-01 | Validation par un professionnel du droit des décisions déléguées du lot n° 1 et des lots suivants (préalable à la bêta) | P0 bêta |
| SEC-08 | Tests d'intrusion, tests adversariaux, montée en charge | P0 bêta |
| DOC-01 | Analyse documentaire (OCR, extraction des faits) et exports (DOCX/PDF) | P1 |
