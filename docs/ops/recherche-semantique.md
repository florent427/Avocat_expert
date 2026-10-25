# Exploitation — recherche sémantique (SRCH-02, ADR 0017)

Le modèle d'embeddings tourne **dans nos processus** (ONNX Runtime, processeur) :
aucun texte du corpus ni aucune question ne quitte l'infrastructure. Seul le
téléchargement initial des fichiers du modèle sort vers `huggingface.co`.

## Mise en place

```bash
export AVX_EMBEDDING_MODEL=multilingual-e5-base@d1287505
export AVX_EMBEDDING_MODEL_DIR=/data/modeles/multilingual-e5-base@d1287505
avx telecharger-modele          # 1,13 Go ; empreintes SHA-256 vérifiées, fichier refusé sinon
avx migrate                     # 0013 : tables des vecteurs
avx calculer-embeddings         # versions courantes sans vecteur (reprise automatique)
avx indexer-recherche --complet # index avec champ vectoriel ; bascule de l'alias
```

* Fichiers du modèle : données uniquement (graphe ONNX, tokenizer JSON),
  épinglés dans `services/api/src/avocat_expert/embedding/models.py` (dépôt,
  révision, empreinte et taille de chaque fichier). Ils sont vérifiés à chaque
  chargement : un fichier altéré empêche le démarrage du canal.
* `calculer-embeddings` accepte un périmètre : `--textes ID…`, `--nature CODE`,
  `--en-vigueur-au AAAA-MM-JJ`, `--max N`. Sans option : tout le corpus
  courant. Le calcul est idempotent (une version déjà vectorisée n'est pas
  reprise) et réutilise le vecteur d'un texte identique (même contexte, même
  texte) déjà calculé.
* Mises à jour : après chaque `avx sync-legi`, `avx calculer-embeddings` puis
  `avx indexer-recherche` (incrémental : reprend aussi les versions qui ont
  reçu leur vecteur depuis la dernière synchronisation).

## Pile locale (`docker compose`)

```bash
cd services/api && uv run avx telecharger-modele --modele multilingual-e5-base@d1287505 \
  --dossier ../../.avx-models/multilingual-e5-base@d1287505 && cd ../..
# .env : AVX_EMBEDDING_MODEL=multilingual-e5-base@d1287505 (AVX_MODELS_DIR, par défaut ./.avx-models)
docker compose up -d --build
docker compose run --rm -e AVX_DATABASE_URL=… migrate avx calculer-embeddings
docker compose run --rm -e AVX_DATABASE_URL=… -e AVX_OPENSEARCH_URL=http://opensearch:9200 migrate avx indexer-recherche --complet
```

Le répertoire des modèles est monté en lecture seule dans l'API. Test de
fumée avec le canal sémantique : `AVX_SMOKE_MODEL_DIR=$PWD/.avx-models
scripts/smoke-compose.sh` (exécuté ainsi en CI).

## Changement de modèle

Les vecteurs sont rangés par modèle : un nouveau modèle se calcule à côté de
l'ancien, sans interruption. Puis `avx indexer-recherche --complet` avec la
nouvelle clé : l'index porte la clé du modèle dans ses métadonnées (`_meta`),
et la recherche refuse de vectoriser une question avec un autre modèle que
celui de l'index (canal signalé « désactivé : reconstruction requise »).
La mise à jour incrémentale refuse aussi un index d'un autre modèle.

## Ressources mesurées (conteneur de développement, 4 cœurs, 2026-10-25)

| | multilingual-e5-base (retenu) | multilingual-e5-small |
|---|---|---|
| Fichiers | 1,13 Go | 487 Mo |
| Vectorisation du corpus (processeur seul) | environ 10 articles/s | 25 à 40 articles/s |
| Vectorisation d'une question | 17 ms (95e centile : 27 ms) | 7 ms |
| Stockage PostgreSQL par texte distinct (vecteur) | 3,1 Ko | 1,5 Ko |
| Canal sémantique complet (question, voisins filtrés, relecture) | 31 ms (95e centile : 40 ms) | — |

Le corpus courant complet (1,8 million de versions) demanderait plusieurs
jours sur 4 cœurs : à répartir sur plusieurs tâches (périmètres disjoints
par `--textes`) ou sur une instance de calcul dédiée, ponctuellement ; les
livraisons quotidiennes (quelques milliers de versions) restent de l'ordre de
la dizaine de minutes.

## Contrôles

```sql
SELECT model_key, count(*) FROM provision_embedding GROUP BY 1;
SELECT count(*) FROM provision_version pv
WHERE pv.sys_to IS NULL AND NOT pv.withdrawn_from_source
  AND NOT EXISTS (SELECT 1 FROM provision_embedding e
                  WHERE e.version_id = pv.id AND e.model_key = 'multilingual-e5-base@d1287505');
```
