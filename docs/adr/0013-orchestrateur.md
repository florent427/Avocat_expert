# ADR 0013 — Orchestrateur typé, évaluation de LangGraph en phase E

**Statut** : acceptée le 2026-10-24 (registre des décisions) · 2026-10-24

## Contexte
Le cahier des charges cite LangGraph « ou orchestrateur typé équivalent ».

## Décision proposée
Démarrer la phase E avec un orchestrateur minimal maison : graphe explicite
d'étapes typées (`AgentTask` → `AgentResult`), exécution déterministe de
l'ordre, reprise sur erreur, budget et délai par étape, journalisation dans
`execution_step`. Évaluer LangGraph sur un prototype équivalent (persistance
d'état, reprise, observabilité, dépendances) avant tout engagement ; la
décision finale sera une nouvelle ADR.
