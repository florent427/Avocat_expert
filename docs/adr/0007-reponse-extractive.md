# ADR 0007 — Réponse extractive par défaut ; génération soumise au vérificateur

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`)

## Décision
* Mode **EXTRACTIF** (V1) : extraits littéraux de versions officielles,
  chacun vérifié ; aucune conclusion juridique générée ; pertinence
  explicitement non évaluée.
* Mode génératif (phase E) : toute affirmation produite par un modèle doit
  être une `Claim` typée avec citations ; le vérificateur indépendant
  (lexverif + agent vérificateur) bloque ou fait reformuler toute affirmation
  insuffisamment fondée ; le mode extractif reste le mode dégradé en cas de
  dépassement de budget (`tenant_budget.degraded_mode`).
* Une question visant une disposition introuvable ne reçoit pas d'autres
  dispositions en remplacement (anti-confusion).
