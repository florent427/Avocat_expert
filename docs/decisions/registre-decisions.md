# Registre des décisions du porteur du projet

| Date | Réf. | Décision | Conséquences |
|---|---|---|---|
| 2026-10-24 | DEC-01 | **Hébergement** : AWS eu-west-3 pour le développement et la recette, **uniquement avec des données publiques ou fictives**. Décision pour la production reportée à l'avis du DPO et d'un conseil (secret professionnel, accès extra-européens). | ADR 0009 amendée. Aucun document client réel avant la décision de production. Architecture maintenue portable (S3 compatible, PostgreSQL, conteneurs, Keycloak). |
| 2026-10-24 | DEC-05 | **PISTE** : création par le porteur d'un compte **bac à sable** (Légifrance, Judilibre) après lecture des CGU. | Connecteurs codés contre le Swagger servi par PISTE une fois l'application créée ; identifiants dans le gestionnaire de secrets, jamais dans le dépôt. Production ultérieure. |
| 2026-10-24 | DEC-02 | **Identité** : Keycloak auto-hébergé (OIDC code + PKCE, MFA obligatoire). | ADR 0011 amendée ; SEC-01 précisé. |
| 2026-10-24 | ADR | **ADR 0001 à 0013 acceptées** (0009 et 0011 amendées par DEC-01 et DEC-02). | — |
| 2026-10-24 | REF-01 | **Référent juridique** : le porteur du projet. | Validation des cas d'évaluation (`validation_juridique`), instruction des risques R1–R6 et de ING-03 sur fiches préparées par l'équipe technique. |

| 2026-10-24 | REF-02 | **Délégation** : le référent juridique demande à Claude de trancher lui-même le lot de validation n° 1 (16 cas, R1–R6, ING-03). | Décisions enregistrées (page de validation, `eval/cases/seed_v0.jsonl` au statut `AVIS_IA_DELEGUE`, `docs/compliance/dependances-reglementaires.md`). Statut distinct de `VALIDE` : la validation par un professionnel reste exigée avant la bêta. |
| 2026-10-24 | ING-03 | Lecture **exclusive** de `DATE_FIN` confirmée (décision déléguée). | Convention de l'ADR 0002 maintenue ; confirmation DILA souhaitable, non bloquante. |

Restent ouvertes : DEC-03 (fournisseur de modèles, phase E), DEC-04
(positionnement et CGU, avant bêta), décision d'hébergement de production.
