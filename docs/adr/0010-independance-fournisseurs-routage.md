# ADR 0010 — Indépendance des fournisseurs de modèles et routage par complexité

**Statut** : proposée — contrats implémentés · 2026-10-24

## Décision
* Aucun SDK de fournisseur dans le code métier : ports `LanguageModel`,
  `Embedder` (phase E/D) avec adaptateurs ; chaque appel produit un
  `AgentUsage` (fournisseur, modèle, jetons entrants/sortants/cache, durée,
  coût en micro-euros, version de la table de prix) persisté dans `usage_record`.
* Agents : contrats `AgentTask`/`AgentResult` stricts et versionnés ; les
  résultats amont sont transmis tels quels.
* Routage : `ComplexityAssessment` → `RoutingDecision` (agents retenus et
  motifs d'exclusion). Une question simple portant sur un article identifié
  n'active que recherche législative + vérificateur.
* Données client : un agent ne transmet un document qu'à un fournisseur
  listé dans `TaskContext.authorized_processors`.
