# Corpus d'évaluation

`cases/seed_v0.jsonl` contient **16 cas techniques** construits à partir des
fixtures LEGI réelles (`fixtures/legi/`). Ils servent à mesurer le
comportement du pipeline (recherche, blocage, intégrité des citations) et à
détecter les régressions. **Aucun de ces cas n'a été validé par un juriste**
(`validation_juridique = NON_VALIDE`) : ils ne mesurent pas la justesse
juridique d'une réponse.

L'objectif du cahier des charges (≥ 500 cas enrichis par des juristes
compétents) reste à atteindre : voir `docs/backlog/backlog-technique.md`
(items QUAL-*) et le format ci-dessous.

## Format (une ligne JSON par cas)

| champ | description |
|---|---|
| `id` | identifiant stable |
| `categorie` | `question_simple`, `cas_complexe`, `droit_ancien`, `disposition_transitoire`, `disposition_differee`, `droit_territorial`, `jurisprudence_contradictoire`, `source_manquante`, `document_adversarial`, `delai_procedural`, `hallucination_reference`, `reformulation_semantique`, `identifiant_officiel`, `reference_article`, `version_mort_nee` |
| `question`, `as_of` | question et date d'appréciation |
| `attendu` | `{"type": "sources", "official_ids": [...]}` (versions attendues) ou `{"type": "blocage", "incertitude_contient": "..."}` |
| `validation_juridique` | `NON_VALIDE`, `VALIDE`, `CONTESTE` |
| `auteur` | auteur du cas (et, après revue, du validateur) |

## Exécution

```bash
cd services/api
AVX_DATABASE_URL=... AVX_LEXVERIF_BIN=... uv run python -m avocat_expert.evaluation.runner ../../eval/cases/seed_v0.jsonl
```

Les métriques sont calculées séparément : rappel@k, MRR, précision@k
(sous-estimée : seules les versions annotées comptent comme pertinentes),
exactitude des blocages, intégrité des citations (contrôles déterministes 1 à
4), conformité temporelle des versions citées, intégrité structurelle des
extraits (pas de phrase introductive orpheline, pas d'item isolé), et ventilation par catégorie.
