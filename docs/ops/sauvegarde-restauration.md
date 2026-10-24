# Sauvegarde et restauration

## Ce qui est testé automatiquement

`services/api/tests/test_backup_restore.py` (exécuté en CI à chaque push) :
sauvegarde logique `pg_dump --format=custom` de la base de test ingérée,
restauration `pg_restore --exit-on-error` dans une base neuve, puis
vérification de l'égalité des comptes de lignes, de l'empreinte du corpus
(identifiant, empreinte du texte, période système de chaque version), du
nombre de politiques RLS, de l'immuabilité de l'historique (DELETE refusé)
et du maintien de `FORCE ROW LEVEL SECURITY`.

Premier résultat (2026-10-24) : **la restauration échouait** (vue BM25
dépendante du `search_path`, que `pg_restore` vide). Corrigé par la migration
0006. Sans cet exercice, le défaut n'aurait été découvert qu'au premier
incident réel.

## Production (AWS RDS, cible)

| Mécanisme | Paramètre (Terraform `modules/database`) |
|---|---|
| Sauvegardes automatiques + restauration à un instant donné (PITR) | `backup_retention_period` = 14 jours (staging), 35 (production) |
| Instantané final avant suppression | `skip_final_snapshot = false`, `deletion_protection = true` |
| Chiffrement des sauvegardes | clé KMS des données |
| Sauvegarde logique hebdomadaire hors RDS | tâche ECS planifiée `pg_dump` vers S3 chiffré (backlog INFRA-06) |

## Exercice de restauration (mensuel, à consigner)

1. Restaurer l'instance à T-24 h dans un sous-réseau isolé
   (`aws rds restore-db-instance-to-point-in-time --use-latest-restorable-time`
   ou heure choisie), sans accès applicatif.
2. Lancer la vérification : comptes de lignes, empreinte du corpus (requête
   `FINGERPRINT` du test), dernière ligne de `ingestion_run`, présence des
   politiques RLS et des triggers d'immuabilité.
3. Mesurer la durée totale (objectif de temps de reprise à fixer : RTO) et
   l'écart de données (objectif de point de reprise : RPO ≤ 5 min avec PITR).
4. Supprimer l'instance restaurée ; consigner date, durées, écarts et
   opérateur dans le registre d'exploitation.

Les données client restaurées restent soumises aux mêmes règles d'accès :
l'exercice est mené par une personne habilitée, sans extraction.
