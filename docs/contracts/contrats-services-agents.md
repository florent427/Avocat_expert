# Contrats des services et des agents

Définis en Pydantic (`services/api/src/avocat_expert/contracts/`), stricts
(`extra="forbid"`, immuables), versionnés (`CONTRACTS_VERSION = 1.0.0`).
Schémas JSON exportés dans `packages/contracts/schemas/` ; la CI échoue s'ils
ne sont pas à jour.

## Services

| Contrat | Champs principaux |
|---|---|
| `SearchRequest` → `SearchResponse` | requête (2–2000 car.), `as_of`, `limit ≤ 50` → `hits[]` (`SourceReference`, extrait littéral, score, canaux), état des canaux, méthode de classement |
| `AnswerRequest` → `SourcedAnswer` | question (≤ 4000), `as_of`, territoire, `max_sources` → statut, résumé, `statements[]` (nature, texte, citation, extrait, vérification, statut), incertitudes, avertissement, recherche |
| `CitationVerificationRequest` → `CitationVerification` | identifiant, extrait, date, territoire → verdict, contrôles, incertitudes, positions (caractères), version en vigueur à la date, versions du moteur et du contrat |

`SourceReference` : source, identifiant de version, identifiant et titre du
document, numéro, période de validité, statut brut, chemin et empreinte du
fichier source, **archive source**, version du connecteur.

## Moteur `lexverif` (JSON, `contract_version = "2"`)

Commandes `verify_citation` et `resolve_at`. Contrôles :
`SOURCE_IDENTIFIEE`, `IDENTIFIANT_RESOLU`, `PASSAGE_PRESENT`,
`APPLICABILITE_TEMPORELLE`, `TERRITOIRE`, `COHERENCE_TEMPORELLE`,
`ADEQUATION_RAISONNEMENT` (toujours `NON_EVALUE`), `CONTRADICTIONS`
(toujours `NON_EVALUE`). Verdict : `CONFORME` / `INCERTAIN` / `NON_CONFORME`.

v2 (ADR 0016) : `valid_from` facultatif (entrée en vigueur non fixée),
`end_undetermined` (abrogation non fixée), `knowledge_date` (dernière
livraison intégrée) ; applicabilité `OUI` / `NON` / `INDETERMINE` et
résolution `UNIQUE` / `AUCUNE` / `AMBIGUE` / `INDETERMINEE`.

## Agents

| Contrat | Rôle |
|---|---|
| `TaskContext` | tenant, dossier, date d'appréciation, territoire, sous-traitants autorisés, budget restant |
| `ComplexityAssessment` | niveau, signaux, besoins (jurisprudence, procédure, documents) |
| `RoutingDecision` | agents retenus (ordre) et motifs d'exclusion |
| `AgentTask` | identifiants de tâche et de trace, agent, version du contrat, contexte, instruction, résultats amont |
| `Claim` | nature (fait, hypothèse, droit applicable, interprétation, recommandation), énoncé, citations, extraits, statut, incertitude |
| `AgentResult` | statut, affirmations, vérifications, questions ouvertes, consommation (`AgentUsage`), horodatage |

Agents prévus : orchestrateur, qualification, recherche législative,
jurisprudence, analyse factuelle, chronologie et preuves, procédure,
argumentation favorable, contradiction, synthèse, vérificateur, rédaction.

Règles : un agent ne reçoit que des contrats ; il ne reformule pas les
résultats amont ; toute `Claim` de nature `DROIT_APPLICABLE` ou
`INTERPRETATION` sans citation vérifiée est `BLOQUEE` ou `INCERTAINE` ; les
contenus issus de documents (client ou adverses) sont transmis comme données
délimitées, jamais comme instructions.
