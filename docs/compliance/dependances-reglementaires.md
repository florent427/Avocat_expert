# Dépendances réglementaires bloquantes

> Document technique d'identification des risques, rédigé par l'équipe
> d'ingénierie le 2026-10-24. **Il ne constitue pas un avis juridique.**
> Chaque point doit être instruit et validé par des professionnels compétents
> (avocat, DPO, RSSI). Le statut de vérification de chaque texte est indiqué ;
> « NON VÉRIFIÉ » signifie que le texte officiel n'a pas pu être consulté
> depuis l'environnement de développement et qu'aucune citation n'en est tirée.

Légende du caractère bloquant : **B-PROD** bloque la mise en production
publique · **B-BETA** bloque une bêta avec données réelles · **B-PHASE**
bloque une phase technique.

| # | Dépendance | Bloque | Responsable | Statut |
|---|---|---|---|---|
| R1 | Périmètre du droit : consultation juridique et rédaction d'actes réservées | B-PROD | Conseil | à instruire |
| R2 | Secret professionnel de l'avocat et hébergement | B-BETA | Conseil, DPO, RSSI | à instruire (ADR 0009) |
| R3 | RGPD : rôles, contrat de sous-traitance, AIPD, registre, durées, droits | B-BETA | DPO | à instruire |
| R4 | Données de justice : interdiction du profilage des magistrats et greffiers, pseudonymisation | B-PHASE (C, jurisprudence) | Conseil | exigence intégrée au modèle |
| R5 | Licences et CGU des sources (LO 2.0, PISTE, Cour de cassation, justice administrative, UE) | B-PHASE (C) | Conseil | partiellement vérifié |
| R6 | Règlement (UE) 2024/1689 (IA) : qualification du système, transparence, maîtrise de l'IA | B-PROD | Conseil | à instruire |
| R7 | Sous-traitants IA (fournisseurs de modèles) : transferts, confidentialité, usage des données | B-PHASE (E) | DPO, achats | à instruire |
| R8 | Données de santé éventuellement présentes dans les pièces (HDS) | B-BETA | DPO | à qualifier |
| R9 | Responsabilité, assurance, CGU/CGV, information de l'utilisateur | B-PROD | Conseil | à instruire |
| R10 | Accessibilité et obligations sectorielles (NIS 2, accessibilité) | B-PROD | Conseil | à qualifier |

## R1 — Activité de consultation juridique

La loi n° 71-1130 du 31 décembre 1971 (titre II, art. 54 et suivants)
réserve la consultation juridique et la rédaction d'actes pour autrui à
certaines professions et sous conditions. Statut : **NON VÉRIFIÉ** (texte
officiel non consulté ce jour).

Conséquences techniques retenues dès la V1 : produit destiné à des
professionnels du droit ; mode extractif sans conclusion ; mention « ne
constitue pas une consultation juridique » ; recommandations typées
`RECOMMANDATION` « à valider par un professionnel ». **Décision DEC-04** :
positionnement et public cible à valider par un conseil avant toute
ouverture.

## R2 — Secret professionnel et hébergement

Les dossiers déposés par les avocats sont couverts par le secret
professionnel. Questions à instruire : compatibilité d'un hébergeur soumis à
un droit extra-européen (accès d'autorités étrangères) ; exigences et
recommandations de la profession ; chiffrement avec gestion des clés
(KMS géré vs clés détenues par le client) ; journalisation des accès ;
réversibilité. **Décision DEC-01**. Aucun document client réel ne doit être
téléversé avant cette décision.

## R3 — RGPD

Hypothèse de travail à valider : le cabinet est responsable de traitement des
données de ses dossiers, la plateforme est sous-traitant (art. 28 :
contrat, instructions documentées, sous-traitants ultérieurs autorisés) ;
pour ses propres données (comptes, facturation), la plateforme est
responsable de traitement. Une **AIPD** (art. 35) est très probablement
requise (données relatives à des procédures, éventuellement à des
infractions — art. 10 —, usage de technologies nouvelles). Décisions
individuelles automatisées (art. 22) : le système n'en prend pas ; à
confirmer dans l'AIPD. Statut des citations d'articles : **NON VÉRIFIÉ**
(texte non consulté ce jour).

Déjà prévu dans le modèle : durée de conservation par organisation,
effacement des pièces (`erased_at`), traces sans contenu, liste des
sous-traitants autorisés par tenant. À faire : SEC-07 (demandes des
personnes, purge, registre).

## R4 — Données de justice

Code de l'organisation judiciaire, art. L111-13, et code de justice
administrative, art. L10 : les données d'identité des magistrats et des
membres du greffe ne peuvent faire l'objet d'une réutilisation ayant pour
objet ou pour effet d'évaluer, d'analyser, de comparer ou de prédire leurs
pratiques professionnelles réelles ou supposées (formulation reprise dans les
CGU de la justice administrative, version du 18/01/2022, vérifiées). Le
texte du COJ n'a pas été consulté sur Légifrance ce jour.

Conséquences techniques retenues : aucun champ structuré d'identité de
magistrat ou de greffier dans `court_decision` ; aucune statistique par
formation nominative ; tests à ajouter lors des connecteurs (ING-05/06) ;
signalement des défauts de pseudonymisation (obligation des CGU de la
justice administrative).

## R5 — Licences et conditions des sources

| Source | Conditions vérifiées | Restant à vérifier |
|---|---|---|
| DILA LEGI/JORF | LO 2.0 ; mention DILA, URL, nom et date du fichier ; dernier stock pour première intégration ; interdiction de réidentification | divergence data.gouv.fr (fr-lo v1) |
| API Légifrance (PISTE) | LO 2.0 + CGU PISTE + CGU API Légifrance + quotas | texte des CGU, quotas |
| Judilibre | LO 2.0 + CGU PISTE + CGU Cour de cassation | texte des CGU, quotas |
| Justice administrative | LO 2.0 + CGU du 18/01/2022 (mentions obligatoires, pseudonymisation, profilage) | — |
| CELLAR / EUR-Lex | Décision 2011/833/UE (réutilisation gratuite, citer la source, ne pas altérer le sens) | avis juridique EUR-Lex, licence actuelle |
| Sources commerciales | — | contrats de licence à négocier ; aucune intégration sans contrat |

Implémenté : provenance complète par version (source, archive horodatée,
chemin, empreinte), licence et obligations stockées dans `legal_source`.

## R6 — Règlement (UE) 2024/1689 sur l'intelligence artificielle

À instruire : (a) la qualification du système au regard de l'annexe III,
point 8 (administration de la justice) — un outil destiné à des avocats
diffère d'un outil destiné aux autorités judiciaires, mais l'usage par ou
pour le compte d'une autorité judiciaire changerait la qualification ;
(b) les obligations de transparence (art. 50) ; (c) l'obligation de maîtrise
de l'IA (art. 4) ; (d) les obligations relatives aux modèles d'IA à usage
général, portées par leurs fournisseurs. Calendrier d'application et
éventuelles modifications ultérieures du règlement : **NON VÉRIFIÉ** —
à consulter au Journal officiel de l'UE (version consolidée CELLAR
disponible : `02024R1689-20260727`).

## R7 — Fournisseurs de modèles

Avant la phase E : DPA, localisation des traitements, absence d'utilisation
des données pour l'entraînement, durées de rétention, sous-traitants
ultérieurs, transferts hors UE. Techniquement : aucun document client n'est
transmis à un fournisseur absent de `organization.authorized_processors`
(contrat `TaskContext`).

## R8 — Données de santé

Les pièces d'un dossier (dommage corporel, droit social) peuvent contenir des
données de santé. L'applicabilité de l'obligation d'hébergement certifié
(HDS) à une plateforme de gestion de dossiers juridiques est **à qualifier**.

## R9 — Responsabilité et information

CGU, limitation de responsabilité, assurance, information claire sur les
limites (mode extractif, pertinence non évaluée, couverture du corpus),
traçabilité des versions citées (déjà en place).

## R10 — Autres cadres

Directive NIS 2 et sa transposition, exigences d'accessibilité : applicabilité
à qualifier selon la taille, les clients et les services proposés.

## Conditions minimales avant toute bêta avec données réelles

1. DEC-01 (hébergement) et DEC-02 (IdP) tranchées ; SEC-01, SEC-03, SEC-04, SEC-07 livrés.
2. AIPD réalisée, contrat de sous-traitance type, registre.
3. CGU des sources acceptées et obligations d'attribution affichées.
4. Corpus d'évaluation validé par des juristes (QUAL-01) et seuils de qualité définis.
5. Tests d'intrusion et revue de sécurité (SEC-08).
