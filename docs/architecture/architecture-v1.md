# Architecture technique V1 — Avocat Expert

> Statut : proposition de l'architecte, **à valider par le porteur du projet**.
> Date : 2026-10-24. Les éléments marqués ✅ sont implémentés et testés dans
> ce dépôt ; ⏳ = prévus (voir backlog) ; ❓ = décision ouverte.

## 1. Objectifs et principes

1. **Exactitude mesurable** : chaque affirmation juridique est rattachée à une
   version précise d'une source officielle, vérifiée par un moteur déterministe ;
   ce qui ne peut pas être vérifié est signalé ou bloqué.
2. **Traçabilité** : identifiant officiel, archive source, empreinte du fichier,
   version du connecteur, lot d'ingestion, date de validité et date
   d'acquisition sont conservés pour chaque version.
3. **Sécurité et confidentialité par conception** : isolation multi-tenant en
   base, aucun texte client dans les traces, aucun envoi de document client à un
   tiers non autorisé explicitement par le tenant.
4. **Indépendance des fournisseurs** : ports (interfaces) entre le métier et les
   fournisseurs (moteur de recherche, embeddings, modèles de langage, IdP).
5. **Simplicité** : un monolithe modulaire Python + un moteur Rust + une
   application web ; découpage en services seulement lorsque la charge ou
   l'isolation l'exigent.

## 2. Vue d'ensemble

```
                    ┌──────────────────────────────────────────────┐
 Navigateur ──TLS──▶│ apps/web (Next.js)                           │
 (desktop/mobile)   │  • UI • proxy serveur (jeton côté serveur)   │
                    └───────────────┬──────────────────────────────┘
                                    │ HTTPS, Bearer (OIDC en cible)
                    ┌───────────────▼──────────────────────────────┐
                    │ services/api (FastAPI, Python)               │
                    │  api/ ─ security (authn, fail-closed)        │
                    │  answer/ ─ réponse sourcée (extractive V1)   │
                    │  search/ ─ hybride : id, n° d'article,       │
                    │            BM25, sémantique (port)           │
                    │  verification/ ─ adaptateur lexverif ────────┼──▶ engine/lexverif (Rust)
                    │  connectors/legi ─ ingestion bitemporelle    │     contrat JSON v1, stdin/stdout
                    │  contracts/ ─ contrats services & agents     │
                    │  observability/ ─ traces, coûts              │
                    │  evaluation/ ─ métriques sur corpus de cas   │
                    └───────┬───────────────────────┬──────────────┘
                            │                       │
                ┌───────────▼─────────┐   ┌─────────▼──────────┐
                │ PostgreSQL 16       │   │ S3 chiffré KMS     │ ⏳ pièces client
                │ + pgvector, FTS fr, │   │ SQS (ingestion,    │ ⏳ traitements
                │ RLS multi-tenant    │   │ analyse documents) │
                └─────────────────────┘   └────────────────────┘
                            ▲
       Sources officielles  │ (lots horodatés, empreintes, licence)
       DILA LEGI (dumps) ✅  │  PISTE Légifrance ⏳  Judilibre ⏳
       Justice administrative (zip XML) ⏳  CELLAR/EUR-Lex ⏳
```

## 3. Composants

### 3.1 Application web — `apps/web` ✅ (prototype)
Next.js 16 / React 19 / TypeScript strict / Tailwind 4. Le navigateur ne
parle qu'à l'application web ; l'appel à l'API se fait côté serveur
(`app/api/answer/route.ts`), le jeton n'est jamais exposé. En-têtes de
sécurité (CSP, `frame-ancestors 'none'`, `nosniff`, `no-referrer`).
Affichage systématique : statut de vérification, contrôles, incertitudes,
avertissement « ne constitue pas une consultation juridique ».

### 3.2 API — `services/api` ✅
* **Authentification** : mode `dev_token` (local/test uniquement, refusé
  au démarrage en staging/production) ; mode `oidc` ⏳ — en attendant, il
  **échoue fermé** (503). L'authentification est résolue avant toute
  autre dépendance (testé).
* **Endpoints** : `POST /v1/search`, `POST /v1/answer`,
  `POST /v1/citations/verify`, `GET /health`.
* **Traces** : chaque réponse écrit `execution_trace`, `execution_step`
  et `usage_record` (empreinte SHA-256 et longueur de la question, jamais
  son texte — testé).

### 3.3 Connecteurs de sources — `connectors/*`
Un sous-paquet par source, versionné (`CONNECTOR_VERSION`), sans logique
métier. V1 : `connectors/legi` (dumps XML DILA), parseur strict
(`defusedxml`, refus des entités), lecture des archives en mémoire (pas
d'extraction disque), liste de suppression appliquée par chemin exact.
Règles d'implémentation : spécification officielle vérifiée avant tout code
(voir `docs/sources/verification-documentation-officielle.md`).

### 3.4 Recherche hybride — `search/` ✅ (partiel)
| Canal | État V1 |
|---|---|
| Identifiant officiel (LEGIARTI, LEGITEXT, JORFTEXT…) | ✅ |
| Numéro d'article (L, R, D, A ; « article 1240 ») + titre du code | ✅ |
| Lexical BM25 (k1=1,2 ; b=0,75) sur tsvector `avx_fr` (français, sans accents) | ✅ |
| Sémantique (pgvector) | ⏳ port défini, **désactivé** tant qu'aucun modèle d'embeddings n'est validé (ADR 0006) |
| Filtres temporels (version en vigueur à la date) | ✅ intervalle semi-ouvert |
| Filtres territoriaux | ❓ la source LEGI ne renseigne pas le champ territorial : jamais présumé |
| Graphe de références | ✅ stockage (`legal_reference`), ⏳ exploitation |
| Reranking | ⏳ (après mesure sur corpus juriste) |
| Déduplication | ✅ par version ; ⏳ inter-sources |
| Vérification des extraits | ✅ par lexverif |

Fusion : correspondances exactes prioritaires, puis RRF (k=60).
Bascule vers OpenSearch : ADR 0005 (seuils de volumétrie/latence).

### 3.5 Moteur déterministe — `engine/lexverif` (Rust) ✅
Contrôles 1 à 5 de l'audit juridique (cahier des charges §6) :
identification de la source, résolution de l'identifiant, présence littérale
du passage (normalisation conservatrice : NFC, apostrophes, espaces ; casse
et ponctuation préservées ; élisions `[…]` ordonnées), applicabilité
temporelle, territoire. Contrôles 6 et 7 (adéquation au raisonnement,
contradictions) renvoyés **`NON_EVALUE`** : jamais présentés comme réussis.
Sous-processus, sans réseau, contrat JSON versionné, champs inconnus refusés.

### 3.6 Réponse sourcée — `answer/` ✅ (mode extractif)
V1 sans modèle génératif : extraits littéraux, chacun vérifié. Une citation
non conforme est bloquée ; une question visant une disposition introuvable
n'obtient pas d'autres dispositions en remplacement ; les lacunes de
couverture (versions déclarées par la source mais non ingérées) sont
signalées. Le mode génératif (phase E) passera obligatoirement par le
vérificateur.

### 3.7 Orchestrateur et agents ⏳ (phase E)
Contrats définis (`contracts/agents.py`, schémas JSON exportés) :
`AgentTask`, `AgentResult`, `Claim` typée (fait / hypothèse / droit
applicable / interprétation / recommandation), `RoutingDecision` avec motifs
d'exclusion. Routage par complexité : les agents ne sont pas exécutés
systématiquement. Choix LangGraph vs orchestrateur typé maison : ADR 0013.

## 4. Données

Voir `docs/data-model/modele-donnees.md`. Points clés : modèle **bitemporel**
(validité juridique `[valid_from, valid_to)` / connaissance `sys_from, sys_to`),
insertion seule protégée par triggers, provenance complète, RLS (FORCE) sur
toutes les tables client, rôle applicatif `avx_app` sans privilège d'écriture
sur le corpus.

## 5. Déploiement cible (⏳, ADR 0009)

AWS `eu-west-3` : ECS Fargate (api, web, workers d'ingestion), RDS
PostgreSQL (chiffré KMS, PITR), S3 (SSE-KMS, accès public bloqué, TLS
obligatoire), SQS (+ DLQ), OpenSearch (phase D), Secrets Manager, ALB + WAF,
CloudTrail, VPC privé avec endpoints. Terraform (`infra/terraform`,
validé syntaxiquement, **jamais appliqué**). ❓ Souveraineté : exposition des
données couvertes par le secret professionnel au droit extra-européen —
décision à prendre avec le DPO et l'ordre (voir conformité).

## 6. Sécurité (résumé)

| Exigence | V1 |
|---|---|
| Autorisation serveur systématique | ✅ dépendance d'authentification sur tous les endpoints métier |
| Isolation multi-tenant | ✅ RLS FORCE + rôle non propriétaire (testé) |
| Immuabilité de l'historique | ✅ triggers (testé) |
| Secrets | ✅ aucun secret versionné (gitleaks en CI), empreinte du jeton uniquement |
| Fichiers téléversés | ⏳ (statut `scan_status`, contrôle de type, antivirus, taille) |
| XML non fiable | ✅ defusedxml (XXE / expansion d'entités refusées, testé) |
| Archives | ✅ lecture en mémoire, fichiers réguliers uniquement, taille bornée |
| Injection de prompt | ✅ mode extractif (aucun LLM) ; ⏳ isolation des contenus non fiables dans les agents |
| SSRF / sorties réseau | ✅ moteur sans réseau ; ⏳ liste blanche d'egress (VPC endpoints, proxy) |
| Traces sans fuite | ✅ empreintes seulement (testé) |
| Chaîne d'approvisionnement | ✅ versions épinglées, `uv exclude-newer`, actions GitHub épinglées par SHA, `npm audit` |

## 7. Qualité et évaluation

`eval/` : format de cas, 16 cas techniques (non validés juridiquement),
métriques séparées (rappel, précision, MRR, exactitude des blocages,
intégrité des citations, conformité temporelle, ventilation par catégorie).
Cible : ≥ 500 cas validés par des juristes + interface de correction (⏳).
