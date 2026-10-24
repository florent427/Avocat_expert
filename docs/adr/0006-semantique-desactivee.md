# ADR 0006 — Canal sémantique désactivé tant qu'aucun modèle d'embeddings n'est validé

**Statut** : proposée — implémentée · 2026-10-24

## Contexte
La recherche sémantique exige un modèle d'embeddings. Pour le corpus public,
le choix porte sur la qualité en français juridique, le coût et la
réversibilité ; pour les documents client, l'envoi à un tiers n'est permis
que s'il est explicitement autorisé et configuré par le tenant.

## Décision
* Port `SemanticSearcher` ; implémentation `DisabledSemanticSearcher` en V1,
  signalée dans chaque réponse (`channels`).
* Sélection d'un modèle en phase D sur le corpus d'évaluation (comparaison
  d'au moins un modèle auto-hébergeable et d'un modèle sous API), dimension
  de `provision_version.embedding` fixée à ce moment.
* Documents client : embeddings uniquement par un modèle auto-hébergé ou un
  sous-traitant listé dans `organization.authorized_processors`.

## Conséquences
Limite mesurée : le cas SEED-014 (« combien de temps » ↔ « durée ») échoue
en lexical seul ; il sert de cas de non-régression pour la phase D.
