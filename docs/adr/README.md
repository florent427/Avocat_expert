# Décisions d'architecture (ADR)

Format : contexte, décision, conséquences, statut. Une ADR acceptée n'est
pas réécrite : elle est remplacée par une nouvelle ADR qui la référence.

Statuts : **Proposée** (en attente de validation du porteur du projet),
**Acceptée**, **Remplacée**. Toutes les ADR ci-dessous sont **proposées**
le 2026-10-24 ; celles marquées « implémentée » sont déjà appliquées dans la
tranche verticale et peuvent être révisées sans coût majeur.

| # | Titre | Statut |
|---|---|---|
| 0001 | Monorepo modulaire | Proposée — implémentée |
| 0002 | Modèle bitemporel, historique immuable | Proposée — implémentée |
| 0003 | LEGI par dumps open data DILA avant l'API PISTE | Proposée — implémentée |
| 0004 | Moteur déterministe Rust en sous-processus, contrat JSON versionné | Proposée — implémentée |
| 0005 | Recherche lexicale BM25 dans PostgreSQL en V1, OpenSearch en phase D | Proposée — implémentée (V1) |
| 0006 | Canal sémantique désactivé tant qu'aucun modèle d'embeddings n'est validé | Proposée — implémentée |
| 0007 | Réponse extractive par défaut ; génération soumise au vérificateur | Proposée — implémentée (extractif) |
| 0008 | Isolation multi-tenant par RLS PostgreSQL | Proposée — implémentée |
| 0009 | AWS eu-west-3 + Terraform, aucun apply sans validation | Proposée — décision de souveraineté ouverte |
| 0010 | Indépendance des fournisseurs de modèles et routage par complexité | Proposée — contrats implémentés |
| 0011 | Authentification OIDC, mode développement fail-closed | Proposée — partiellement implémentée |
| 0012 | Traçabilité sans fuite de données confidentielles | Proposée — implémentée |
| 0013 | Orchestrateur typé, évaluation de LangGraph en phase E | Proposée |
