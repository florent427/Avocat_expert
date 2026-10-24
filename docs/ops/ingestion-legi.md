# Exploitation — ingestion LEGI

## Première intégration et mises à jour

```bash
avx migrate
avx sync-legi --dossier /data/legi --simulation   # plan, sans téléchargement
avx sync-legi --dossier /data/legi                # stock puis deltas, dans l'ordre
```

* Première intégration : **dernier stock** (`Freemium_legi_global_…`), puis
  toutes les livraisons incrémentales postérieures (fiche DILA LEGI : « utiliser
  le dernier stock pour une première intégration »). Les livraisons antérieures
  au stock ne sont pas appliquées.
* Mises à jour : livraisons postérieures à la dernière intégrée, dans l'ordre
  croissant (documentation XML DILA). Une archive antérieure à la dernière
  livraison intégrée est **refusée** : elle remplacerait une connaissance plus
  récente par une plus ancienne.
* Téléchargement : HTTPS, hôte `echanges.dila.gouv.fr` uniquement (redirections
  comprises), taille maximale, fichier `.partiel` renommé une fois complet.

## Incidents

| Situation | Comportement | Action |
|---|---|---|
| Processus arrêté pendant une ingestion | lots déjà validés conservés ; ingestion marquée `FAILED` (ou `RUNNING` orpheline) | relancer la même commande : reprise après le dernier lot validé (`resume_count` incrémenté) |
| Archive modifiée entre deux tentatives | empreinte différente : nouvelle ingestion complète | aucune |
| Point de reprise incohérent | `ResumeMismatchError`, rien n'est écrit | examiner `ingestion_run.last_committed_path` ; remettre `files_committed` à 0 pour une reprise complète (idempotente) |
| Fichier rejeté (format) | compté dans `rejected`, détail dans `stats.errors` ; code retour 1 | analyser avant la livraison suivante |
| Deux ingestions simultanées | la seconde attend le verrou consultatif de la source | aucune |

Un même élément présent dans deux branches d'une livraison (le stock du
2025-07-13 en contient 12 143 articles et 1 945 sections) : la copie dont le
fichier est le plus récent dans l'archive fait foi (`stale_duplicate` compte
les copies périmées écartées). Un répertoire extrait ne conserve pas ces
horodatages de manière fiable : l'ordre de lecture s'applique alors.

Une ingestion répétée de la même archive est idempotente : aucune écriture
pour un fichier déjà connu à l'identique.

## Contrôles après ingestion

```sql
SELECT archive_name, status, stats->'by_kind', files_committed, resume_count, finished_at - started_at
FROM ingestion_run ORDER BY started_at DESC LIMIT 5;
SELECT avx_knowledge_date('DILA_LEGI');   -- date de connaissance du corpus
```

L'option `--hors-sequence` d'`avx ingest-legi` désactive le contrôle d'ordre :
réservée aux fixtures et livraisons de test, jamais en recette ni en production.
