# Backlog technique priorisé

P0 = bloquant pour la phase suivante · P1 = nécessaire avant bêta · P2 = après bêta.
« Validation » = action humaine (porteur, juriste, DPO, RSSI) requise.

## Décisions à prendre (porteur du projet)
| ID | Sujet | Prio | Dépend de |
|---|---|---|---|
| DEC-01 | Souveraineté de l'hébergement (AWS vs SecNumCloud) au regard du secret professionnel | P0 | DPO, conseil |
| DEC-02 | Fournisseur d'identité OIDC | P0 | DEC-01 |
| DEC-03 | Fournisseur(s) de modèles et conditions contractuelles (DPA, absence d'entraînement, localisation) | P0 phase E | DEC-01 |
| DEC-04 | Positionnement (outil réservé aux professionnels du droit) et CGU | P0 bêta | conseil |
| DEC-05 | Ouverture d'un compte PISTE (Légifrance, Judilibre) et acceptation des CGU | P0 phase C | — |

## Conformité
| ID | Tâche | Prio |
|---|---|---|
| COMP-01 | Information « système d'IA » (art. 50 §1) et marquage lisible par machine des sorties générées (art. 50 §2, règlement IA modifié par 2026/1744) avant activation du mode génératif | P0 phase E |
| COMP-02 | Registre de qualification du système au regard de l'annexe III (point 8) et de l'art. 6 §3, revu à chaque nouvel usage ou client | P0 bêta (validation) |
| COMP-03 | Rejouer les deltas LEGI postérieurs au 2025-07-13 sur COJ/CJA/loi 71-1130 ; extraire art. 56–66 de la loi 71-1130 | P1 |

## Phase B — socle
| ID | Tâche | Prio |
|---|---|---|
| INFRA-01 | CI GitHub Actions verte sur la branche de travail puis protégée sur `main` (règles de branche, revues obligatoires) | P0 |
| INFRA-02 | Construction et scan des images (API, web), SBOM, signature | P0 |
| INFRA-03 | Terraform : réseau privé, RDS, ECS, ALB+WAF, Secrets Manager, CloudTrail, budgets — sans apply avant validation | P0 |
| INFRA-04 | OpenTelemetry (traces, métriques) avec liste blanche d'attributs | P1 |
| INFRA-05 | Sauvegardes RDS + test de restauration documenté | P1 |
| WEB-01 | ESLint, tests de composants, tests E2E Playwright | P1 |
| WEB-03 | Génération des types TypeScript depuis `packages/contracts` | P1 |

## Phase C — corpus
| ID | Tâche | Prio |
|---|---|---|
| ING-01 | Textes et sections LEGI (`LEGITEXT` version/struct, `LEGISCTA`) | P0 |
| ING-02 | Ingestion du stock Freemium (1,1 Go) en flux + deltas ordonnés, reprise sur incident | P0 |
| ING-03 | Confirmation de la sémantique DATE_FIN (inclusive/exclusive) et des sentinelles (2999-12-31, 2222-02-22) auprès de la DILA | P0 (validation) |
| ING-04 | JORF | P1 |
| ING-05 | Judilibre (spécification OpenAPI 1.2.5 vérifiée ; KeyId PISTE) | P1 |
| ING-06 | Justice administrative (archives zip XML mensuelles, CGU 18/01/2022) | P1 |
| ING-07 | CELLAR/EUR-Lex (SPARQL + REST CELLAR vérifiés) | P1 |
| ING-08 | Qualification territoriale (outre-mer, Alsace-Moselle) avec validation juriste | P1 |
| ING-09 | Exploitation du graphe de références (résolution des cibles, transferts) | P1 |
| ING-10 | Supervision de fraîcheur (dernier delta ingéré, écarts) | P1 |

## Phase D — recherche et évaluation
| ID | Tâche | Prio |
|---|---|---|
| SRCH-01 | Adaptateur OpenSearch (analyseur français), comparaison avec BM25 PostgreSQL | P0 |
| SRCH-02 | Sélection et évaluation d'un modèle d'embeddings ; activation pgvector (SEED-014) | P0 |
| SRCH-03 | Reranking (après mesure) | P1 |
| QUAL-01 | Corpus ≥ 500 cas rédigés/validés par des juristes (toutes catégories du cahier des charges) | P0 (validation) |
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
| SEC-01 | OIDC + MFA + RBAC (ADR 0011) | P0 |
| SEC-02 | Journal d'accès alimenté par toutes les routes | P0 |
| SEC-03 | Positionnement de `app.tenant_id` par transaction (`SET LOCAL`) et tests de pool | P0 |
| SEC-04 | Téléversement : liste blanche de types, taille, antivirus, stockage S3 chiffré, URL présignées courtes | P0 |
| SEC-05 | Contrôle des sorties réseau (egress) et protection SSRF des connecteurs | P0 |
| SEC-06 | HMAC par tenant pour les empreintes de données client | P1 |
| SEC-07 | Demandes RGPD (accès, effacement), politique de conservation, purge | P0 |
| SEC-08 | Tests d'intrusion, tests adversariaux, montée en charge | P0 bêta |
| DOC-01 | Analyse documentaire (OCR, extraction des faits) et exports (DOCX/PDF) | P1 |
