# ADR 0017 — Canal sémantique : embeddings auto-hébergés, vecteurs dans PostgreSQL, voisins dans OpenSearch

**Statut** : proposée le 2026-10-25 — implémentée (décision du porteur DEC-07 :
modèle auto-hébergé). Complète l'ADR 0006.

## Contexte

Sur le corpus complet, les questions en langage naturel n'aboutissent pas par
le seul canal lexical (phase C, § 4 ; mesure ci-dessous : rappel@10 de 0,18).
Le porteur a écarté les API d'embeddings tierces (DEC-07) : un texte ou une
question envoyés à un tiers en feraient un sous-traitant (article 28 RGPD),
et les questions des avocats peuvent contenir des éléments couverts par le
secret professionnel.

## Décision

1. **Calcul local** avec ONNX Runtime (processeur), fichiers du modèle
   épinglés (dépôt, révision, empreinte SHA-256 et taille de chaque fichier,
   `embedding/models.py`), vérifiés au téléchargement et à chaque chargement.
   Uniquement des fichiers de données (graphe ONNX, tokenizer JSON) : ni
   PyTorch, ni sérialisation pickle, ni code fourni par le dépôt du modèle.
   Seule sortie réseau : le téléchargement initial (`huggingface.co`,
   `*.hf.co`), opération d'exploitation ; l'image d'exécution fixe
   `HF_HUB_OFFLINE=1`.
2. **Modèle** : `intfloat/multilingual-e5-base` (licence MIT, 768 dimensions,
   révision `d1287505`), voir § Sélection.
3. **Texte vectorisé** : intitulé du texte, chemin dans le plan, numéro, texte
   de l'article, préfixe de rôle du modèle ; troncature à 512 jetons
   (23 articles sur un échantillon de 500 du code du travail la dépassent ;
   leur fin n'est pas vectorisée).
4. **Vecteurs dans PostgreSQL** (migration 0013), adressés par l'empreinte du
   texte exact soumis au modèle, rangés par modèle, en insertion seule ; chaque
   version d'article indique le texte vectorisé. Pas de colonne dans
   `provision_version` : une mise à jour par vecteur réécrirait chaque ligne
   (7,8 Go) et lierait le corpus à un seul modèle. La colonne réservée en
   0001, jamais alimentée, est supprimée.
5. **Plus proches voisins dans OpenSearch** (champ `knn_vector`, HNSW faiss,
   cosinus), dans le même index que le canal lexical : filtres de date et de
   texte appliqués pendant le parcours du graphe (« efficient filtering » de
   la documentation k-NN 3.x, recherche exacte si le filtre est très
   sélectif). pgvector n'est pas utilisé pour la recherche : son index HNSW
   applique les conditions après le parcours du graphe (balayages itératifs
   depuis la version 0.8, bornés en nombre de lignes), mal adapté à un filtre
   très sélectif comme un texte nommé (le code du travail : 1,7 % des versions
   en vigueur).
6. **Cohérence** : l'index porte la clé du modèle (`_meta`) ; une question
   n'est jamais vectorisée par un autre modèle que celui de l'index (canal
   désactivé et signalé), la mise à jour incrémentale le refuse aussi.
7. **Fusion** : rangs réciproques (RRF, k = 60) avec le canal lexical, après
   correspondances exactes. Un résultat sémantique dont la similarité est
   inférieure de plus de `SEMANTIC_MARGIN` à la meilleure est écarté.
   Chaque disposition citée indique par quel canal elle a été retrouvée ; la
   synthèse signale les dispositions retrouvées par proximité de sens seule.
8. **Documents client** (hors périmètre actuel) : même modèle local ; aucun
   envoi à un tiers (ADR 0006 inchangée sur ce point).

## Sélection

Candidats auto-hébergeables multilingues sous licence MIT, distribués au
format ONNX par leurs auteurs. Jeu `eval/cases/echelle_v0.jsonl` : 28
questions en langage naturel formulées sans le vocabulaire de l'article
attendu (codes du travail, civil, pénal, de la consommation, de commerce).
Classement par le seul canal sémantique dans un ensemble commun de 3 836
articles en vigueur (articles attendus, 30 premiers résultats lexicaux de
chaque question sur le corpus complet, 3 000 articles de codes tirés au
hasard) ; mêmes textes vectorisés, 512 jetons au plus.

| Modèle | Dimension | Fichiers | MRR@10 | Rappel@1 | Rappel@10 | Débit relatif |
|---|---|---|---|---|---|---|
| multilingual-e5-small | 384 | 0,49 Go | 0,363 | 0,250 | 0,607 | 2,4 |
| multilingual-e5-base (int8, avx512_vnni) | 768 | 0,28 Go | 0,411 | 0,286 | 0,679 | 3,3 |
| **multilingual-e5-base** | 768 | 1,13 Go | 0,519 | 0,429 | 0,821 | 1 |
| bge-m3 | 1024 | 2,28 Go | 0,591 | 0,429 | 0,857 | 0,4 |
| *lexical seul, corpus complet (repère)* | | | *0,121* | | *0,179* | |

Débit relatif mesuré sur 4 cœurs, sans processeur graphique, en partie sous
charge concurrente : ordres de grandeur (e5-base seul :
environ 10 articles/s). Le canal lexical est mesuré sur le corpus complet,
plus difficile que l'ensemble commun : le repère montre l'ordre de grandeur
du manque, pas un écart exact.

**e5-base retenu** : écart net avec e5-small (6 questions de plus trouvées
dans les 10 premiers) et avec sa version quantifiée ; bge-m3 fait un peu
mieux (une question de plus dans les 10 premiers, même rappel@1), écart non
significatif sur 28 questions, pour un coût de calcul 2,5 fois supérieur, des
vecteurs un tiers plus grands et un modèle deux fois plus lourd. À réévaluer
sur le corpus annoté par des juristes (QUAL-01), et en particulier pour les
articles longs (bge-m3 accepte 8 192 jetons).

## Conséquences

* Aucun sous-traitant supplémentaire pour la recherche sémantique.
* Coût de calcul supporté par nos instances (voir `docs/ops/recherche-semantique.md`).
* Un changement de modèle impose un recalcul complet et une reconstruction de
  l'index ; l'ancien modèle reste servi pendant le calcul.
* La similarité n'est pas une pertinence juridique : les dispositions
  retrouvées par ce canal sont vérifiées comme les autres (moteur lexverif),
  et l'avertissement « pertinence juridique non évaluée » demeure.
