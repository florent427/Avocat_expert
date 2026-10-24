# Dépendances réglementaires bloquantes

> Document technique d'identification des risques, rédigé par l'équipe
> d'ingénierie le 2026-10-24. **Il ne constitue pas un avis juridique.**
> Textes consultés via les exports officiels (Légifrance et EUR-Lex étant
> inaccessibles) : stock DILA LEGI `Freemium_legi_global_20250713-140000`
> pour le droit français (**état au 2025-07-13 : modifications ultérieures
> non contrôlées**) et CELLAR (Office des publications de l'UE) pour le droit
> de l'Union.
> Chaque point doit être instruit et validé par des professionnels compétents
> (avocat, DPO, RSSI). Le statut de vérification de chaque texte est indiqué ;
> « NON VÉRIFIÉ » signifie que le texte officiel n'a pas pu être consulté
> depuis l'environnement de développement et qu'aucune citation n'en est tirée.

Légende du caractère bloquant : **B-PROD** bloque la mise en production
publique · **B-BETA** bloque une bêta avec données réelles · **B-PHASE**
bloque une phase technique.

| # | Dépendance | Bloque | Responsable | Statut |
|---|---|---|---|---|
| R1 | Périmètre du droit : consultation juridique et rédaction d'actes réservées | B-PROD | Conseil | art. 54–55 vérifiés ; qualification à instruire |
| R2 | Secret professionnel de l'avocat et hébergement | B-BETA | Conseil, DPO, RSSI | à instruire (ADR 0009) |
| R3 | RGPD : rôles, contrat de sous-traitance, AIPD, registre, durées, droits | B-BETA | DPO | art. 22, 28, 35 vérifiés ; à instruire |
| R4 | Données de justice : interdiction du profilage des magistrats et greffiers, pseudonymisation | B-PHASE (C, jurisprudence) | Conseil | textes vérifiés ; exigence intégrée au modèle |
| R5 | Licences et CGU des sources (LO 2.0, PISTE, Cour de cassation, justice administrative, UE) | B-PHASE (C) | Conseil | partiellement vérifié |
| R6 | Règlement (UE) 2024/1689 (IA), modifié par le règlement (UE) 2026/1744 : qualification, transparence, maîtrise de l'IA | B-PROD | Conseil | textes vérifiés ; qualification à instruire |
| R7 | Sous-traitants IA (fournisseurs de modèles) : transferts, confidentialité, usage des données | B-PHASE (E) | DPO, achats | à instruire |
| R8 | Données de santé éventuellement présentes dans les pièces (HDS) | B-BETA | DPO | à qualifier |
| R9 | Responsabilité, assurance, CGU/CGV, information de l'utilisateur | B-PROD | Conseil | à instruire |
| R10 | Accessibilité et obligations sectorielles (NIS 2, accessibilité) | B-PROD | Conseil | à qualifier |

## R1 — Activité de consultation juridique

Loi n° 71-1130 du 31 décembre 1971 — **VÉRIFIÉ pour les art. 54 et 55**
(stock LEGI du 2025-07-13) :

* art. 54 (version en vigueur depuis le 2020-01-01) : « Nul ne peut,
  directement ou par personne interposée, à titre habituel et rémunéré,
  donner des consultations juridiques ou rédiger des actes sous seing privé,
  pour autrui : 1° S'il n'est titulaire d'une licence en droit ou s'il ne
  justifie, à défaut, d'une compétence juridique appropriée […] conformément
  aux articles 56 à 66. » ;
* art. 55 : obligation d'assurance, « également applicable[s] à toute personne
  qui, à titre habituel et gratuit, donne des consultations juridiques ».

**NON VÉRIFIÉ** : art. 56 à 66 (catégories autorisées), dispositions pénales,
et toute jurisprudence sur la qualification d'un outil logiciel en
« consultation juridique ». La qualification du produit relève d'un conseil.

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
responsable de traitement.

Textes **VÉRIFIÉS** (CELLAR `32016R0679`, aucun acte modificatif indexé) :
art. 28 §1 (« uniquement appel à des sous-traitants qui présentent des
garanties suffisantes »), §2 (pas de sous-traitant ultérieur « sans
l'autorisation écrite préalable, spécifique ou générale, du responsable du
traitement »), §3 (contrat ou autre acte juridique) ; art. 35 §1 (analyse
d'impact préalable lorsqu'un traitement, « en particulier par le recours à de
nouvelles technologies », est susceptible d'engendrer un risque élevé) ;
art. 22 §1 (droit de ne pas faire l'objet d'une décision « fondée
exclusivement sur un traitement automatisé […] produisant des effets
juridiques »).

Une **AIPD** paraît très probablement nécessaire (technologies nouvelles,
données de procédures, éventuellement d'infractions) — à confirmer par le
DPO au regard des listes de la CNIL et des lignes directrices du CEPD
(**non consultées**). Le système ne prend pas de décision individuelle
automatisée : à documenter dans l'AIPD.

Déjà prévu dans le modèle : durée de conservation par organisation,
effacement des pièces (`erased_at`), traces sans contenu, liste des
sous-traitants autorisés par tenant. À faire : SEC-07 (demandes des
personnes, purge, registre).

## R4 — Données de justice

**VÉRIFIÉ** (stock LEGI du 2025-07-13) — COJ art. L111-13
(`LEGIARTI000038311162`, en vigueur depuis le 2019-03-25) et CJA art. L10
(`LEGIARTI000038311171`) : « Les données d'identité des magistrats et des
membres du greffe ne peuvent faire l'objet d'une réutilisation ayant pour
objet ou pour effet d'évaluer, d'analyser, de comparer ou de prédire leurs
pratiques professionnelles réelles ou supposées. » Pour le COJ : « La
violation de cette interdiction est punie des peines prévues aux articles
226-18, 226-24 et 226-31 du code pénal […] » ; occultation préalable des
« nom et prénoms des personnes physiques mentionnées dans la décision,
lorsqu'elles sont parties ou tiers ». La même interdiction figure dans les
CGU de la justice administrative (18/01/2022).

**NON VÉRIFIÉ** : décrets d'application (R. 111-10 s. COJ, R. 741-13 à
R. 741-15 CJA), arrêté du 28 avril 2021, et modifications postérieures au
2025-07-13.

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

**VÉRIFIÉ** via CELLAR (texte JO, version consolidée `02024R1689-20260727`,
« outil de documentation » sans effet juridique, et acte modificatif) le
2026-10-24 ; le point clé a été recontrôlé indépendamment.

**Fait majeur** : le règlement est modifié par le **règlement (UE) 2026/1744**
du 8 juillet 2026 (« train de mesures omnibus numérique sur l'IA », JO L du
24.7.2026). Conséquences sur le calendrier (art. 113 consolidé) :

* application générale : 2 août 2026 (inchangée) ;
* chapitre III, sections 1 à 3 (obligations des systèmes à haut risque) :
  **2 décembre 2027** pour l'annexe III (dont le point 8), 2 août 2028 pour
  l'annexe I ;
* art. 50 (transparence) : applicable depuis le 2 août 2026 ; pour les
  systèmes générant du contenu de synthèse mis sur le marché avant cette date,
  mise en conformité à l'art. 50 §2 d'ici au 2 décembre 2026 (art. 111 §4) ;
* art. 4 (maîtrise de l'IA) réécrit : les fournisseurs et déployeurs
  « prennent des mesures pour favoriser le développement de la maîtrise de
  l'IA par leur personnel » (le texte initial disait « garantir »).

Qualification à instruire :

* annexe III, point 8 a) (inchangé) : systèmes « destinés à être utilisés par
  les autorités judiciaires ou en leur nom, pour les aider à rechercher et à
  interpréter les faits ou la loi » — un outil destiné aux avocats n'est pas
  visé par cette lettre, mais toute offre à des juridictions ou pour leur
  compte changerait l'analyse ;
* art. 6 §3 : dérogation pour un système de l'annexe III sans « risque
  important de préjudice », mais un système de l'annexe III « est toujours
  considéré comme étant à haut risque lorsqu'il effectue un profilage de
  personnes physiques » ;
* art. 50 §1 : information des personnes qu'elles interagissent avec un
  système d'IA ; §2 : marquage lisible par machine des contenus textuels de
  synthèse — pertinent dès l'activation d'un mode génératif (phase E).

**NON VÉRIFIÉ** : nouveaux points b bis) et b ter) de l'art. 5 §1 (applicables
au 2 décembre 2026), actes délégués et lignes directrices de la Commission
(art. 6 §3, art. 50), exhaustivité de l'indexation des actes modificatifs par
CELLAR.

Conséquences techniques retenues : statut « résultat produit
automatiquement » déjà affiché ; ajout au backlog de COMP-01 (information
art. 50 §1 et marquage des sorties générées, art. 50 §2, avant la phase E) et
COMP-02 (registre de qualification du système, mis à jour à chaque nouvel
usage ou client).

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

## Décisions du 2026-10-24 (Claude, sur délégation du référent juridique)

> Prises par Claude à la demande du porteur du projet, référent juridique,
> après vérification des sources sur Légifrance (connecteur Openlegi) et
> CELLAR. **Elles encadrent le développement ; elles ne constituent pas la
> validation par un professionnel exigée avant la bêta.**

| # | Décision | Sources vérifiées le 2026-10-24 |
|---|---|---|
| R1 | **Approuvée.** Produit réservé aux professionnels, mode documentaire. Un mode génératif appliquant le droit à la situation personnelle d'un non-professionnel franchirait la ligne ; avis externe obligatoire avant toute ouverture à des non-professionnels. | Loi 71-1130 art. 54 ; Cass. 1re civ., 8 févr. 2023, n° 21-22.828 (« informations à caractère documentaire sur l'état du droit et de la jurisprudence ») ; Cass. 1re civ., 23 sept. 2020, n° 19-12.894 (Demander justice ; « bibliothèque documentaire » dans les motifs de la cour d'appel) ; Cass. 1re civ., 5 juill. 2017, n° 16-22.878. Sanction : art. 66-2 → peines de l'art. 72 → art. 433-17 C. pén. ; **art. 66-2 en abrogation différée au 01/02/2027**, texte de remplacement non identifié. |
| R2 | **Approuvée.** Aucune donnée client réelle avant décision d'hébergement ; exigences : clés hors hébergeur, UE, contestation des demandes étrangères, journal d'accès pour le cabinet, réversibilité, effacement prouvé. | Loi 71-1130 art. 66-5 (« toutes les pièces du dossier sont couvertes par le secret professionnel »). |
| R3 | **Amendée.** Cabinet responsable, plateforme sous-traitante ; **aucune réutilisation des données client pour les besoins propres de la plateforme** (évaluation, amélioration, entraînement) sans accord exprès ; AIPD avant bêta. | RGPD art. 22, 28, 35 ; loi 78-17 art. 46, 2° (auxiliaires de justice). |
| R4 | **Amendée.** Refus des requêtes visant nommément un magistrat ou un greffier ; pas d'indexation de la composition des juridictions ; aucun tri, filtre ou regroupement par juge ou formation nominative ; pas de masquage des noms dans le texte affiché. | COJ L111-13 ; CJA L10 ; loi 78-17 art. 46, 5° (ni objet ni effet de réidentification). |
| R5 | **Approuvée.** Mentions cumulées Licence Ouverte + fiche DILA ; texte jamais altéré. | CRPA art. L322-1 (non-altération, sens non dénaturé, sources et date de dernière mise à jour). |
| R6 | **Amendée.** Hors annexe III point 8 a) pour un outil vendu aux avocats ; juridictions exclues comme clientes ; mention « système d'IA » affichée (fait) ; aucune analyse des juges ; plateforme = fournisseur, cabinets = déployeurs ; marquage des sorties générées avant tout mode génératif. | Règlement (UE) 2024/1689 consolidé (modifié par 2026/1744) : annexe III pt 8, art. 6 §3, art. 50. |

## Conditions minimales avant toute bêta avec données réelles

1. DEC-01 (hébergement) et DEC-02 (IdP) tranchées ; SEC-01, SEC-03, SEC-04, SEC-07 livrés.
2. AIPD réalisée, contrat de sous-traitance type, registre.
3. CGU des sources acceptées et obligations d'attribution affichées.
4. Corpus d'évaluation validé par des juristes (QUAL-01) et seuils de qualité définis.
5. Tests d'intrusion et revue de sécurité (SEC-08).
