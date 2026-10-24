# Décisions d'architecture (ADR)

Format : contexte, décision, conséquences, statut. Une ADR acceptée n'est
pas réécrite : elle est remplacée par une nouvelle ADR qui la référence.

Statuts : **Proposée**, **Acceptée**, **Remplacée**. Les ADR 0001 à 0013 ont
été **acceptées par le porteur du projet le 2026-10-24**
(`docs/decisions/registre-decisions.md`), 0009 et 0011 étant amendées.

| # | Titre | Statut |
|---|---|---|
| 0001 | Monorepo modulaire | Acceptée — implémentée |
| 0002 | Modèle bitemporel, historique immuable | Acceptée — implémentée |
| 0003 | LEGI par dumps open data DILA avant l'API PISTE | Acceptée — implémentée |
| 0004 | Moteur déterministe Rust en sous-processus, contrat JSON versionné | Acceptée — implémentée |
| 0005 | Recherche lexicale BM25 dans PostgreSQL en V1, OpenSearch en phase D | Acceptée — implémentée (V1) |
| 0006 | Canal sémantique désactivé tant qu'aucun modèle d'embeddings n'est validé | Acceptée — implémentée |
| 0007 | Réponse extractive par défaut ; génération soumise au vérificateur | Acceptée — implémentée (extractif) |
| 0008 | Isolation multi-tenant par RLS PostgreSQL | Acceptée — implémentée |
| 0009 | AWS eu-west-3 + Terraform, aucun apply sans validation | Acceptée — amendée (DEC-01) ; hébergement de production ouvert |
| 0010 | Indépendance des fournisseurs de modèles et routage par complexité | Acceptée — contrats implémentés |
| 0011 | Authentification OIDC, mode développement fail-closed | Acceptée — amendée (DEC-02 Keycloak) ; partiellement implémentée |
| 0012 | Traçabilité sans fuite de données confidentielles | Acceptée — implémentée |
| 0013 | Orchestrateur typé, évaluation de LangGraph en phase E | Acceptée |
