//! Vérification déterministe d'une citation.

use crate::contract::{
    Check, CheckName, Command, Outcome, QuoteSpan, Request, Response, ResultBody, Verdict,
    VerifyCitationPayload, VerifyCitationResult, CONTRACT_VERSION,
};
use crate::identifiers::classify;
use crate::normalize::normalize;
use crate::temporal::{resolve_at, InForce, Resolution};

/// Longueur minimale (caractères non blancs) d'un segment cité pour qu'une
/// correspondance soit probante. En deçà, un extrait comme « le » serait
/// trouvé dans presque tout texte.
pub const MIN_SEGMENT_LEN: usize = 20;

/// Marqueurs d'élision acceptés dans une citation.
const ELISIONS: [&str; 4] = ["[...]", "[…]", "(...)", "(…)"];

pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");

pub fn handle(request: Request) -> Response {
    if request.contract_version != CONTRACT_VERSION {
        return Response::Error {
            contract_version: CONTRACT_VERSION,
            engine_version: ENGINE_VERSION,
            error: format!(
                "version de contrat non prise en charge : {} (attendue : {})",
                request.contract_version, CONTRACT_VERSION
            ),
        };
    }
    let result = match request.command {
        Command::VerifyCitation(payload) => ResultBody::VerifyCitation(verify_citation(&payload)),
        Command::ResolveAt(payload) => ResultBody::ResolveAt(resolve_at(
            &payload.versions,
            payload.as_of,
            payload.knowledge_date,
        )),
    };
    Response::Ok {
        contract_version: CONTRACT_VERSION,
        engine_version: ENGINE_VERSION,
        result,
    }
}

fn check(name: CheckName, outcome: Outcome, detail: impl Into<String>) -> Check {
    Check {
        check: name,
        outcome,
        detail: detail.into(),
    }
}

fn split_segments(quote: &str) -> Vec<String> {
    let mut parts = vec![quote.to_string()];
    for marker in ELISIONS {
        parts = parts
            .iter()
            .flat_map(|p| p.split(marker).map(str::to_string).collect::<Vec<_>>())
            .collect();
    }
    parts
        .into_iter()
        .map(|p| normalize(&p))
        .filter(|n| !n.text.is_empty())
        .map(|n| n.text)
        .collect()
}

enum PassageOutcome {
    Found(QuoteSpan),
    NotFound(String),
    TooShort(String),
}

fn find_passage(text: &str, quote: &str) -> PassageOutcome {
    let segments = split_segments(quote);
    if segments.is_empty() {
        return PassageOutcome::TooShort("citation vide".into());
    }
    if let Some(short) = segments
        .iter()
        .find(|s| s.chars().filter(|c| !c.is_whitespace()).count() < MIN_SEGMENT_LEN)
    {
        return PassageOutcome::TooShort(format!(
            "segment trop court pour être probant ({} caractères significatifs minimum) : « {} »",
            MIN_SEGMENT_LEN, short
        ));
    }
    let haystack = normalize(text);
    let mut cursor = 0usize;
    let mut first_span: Option<QuoteSpan> = None;
    for (index, segment) in segments.iter().enumerate() {
        let Some(relative) = haystack.text[cursor..].find(segment.as_str()) else {
            return PassageOutcome::NotFound(format!(
                "segment {} introuvable dans le texte de la version (après normalisation des espaces et apostrophes)",
                index + 1
            ));
        };
        let start = cursor + relative;
        let end = start + segment.len();
        if index == 0 {
            let occurrences = haystack.text.matches(segment.as_str()).count();
            let (orig_start, orig_end) = haystack.original_span(start, end).unwrap_or((0, 0));
            first_span = Some(QuoteSpan {
                start: orig_start,
                end: orig_end,
                occurrences,
            });
        }
        cursor = end;
    }
    match first_span {
        Some(span) => PassageOutcome::Found(span),
        None => PassageOutcome::NotFound("aucun segment exploitable".into()),
    }
}

pub fn verify_citation(payload: &VerifyCitationPayload) -> VerifyCitationResult {
    let claim = &payload.citation;
    let mut checks = Vec::new();
    let mut uncertainties = Vec::new();
    let mut quote_span = None;

    // 1. Identification de la source.
    let family = classify(&claim.official_id);
    checks.push(match family {
        Some(f) => check(
            CheckName::SourceIdentifiee,
            Outcome::Ok,
            format!("famille {f:?}"),
        ),
        None => check(
            CheckName::SourceIdentifiee,
            Outcome::Echec,
            format!("identifiant non reconnu : « {} »", claim.official_id),
        ),
    });

    // 2. Résolution de l'identifiant officiel.
    let candidate = payload.candidate.as_ref().filter(|c| {
        c.official_id == claim.official_id && c.period.official_id == claim.official_id
    });
    checks.push(match (&payload.candidate, candidate) {
        (_, Some(_)) => check(
            CheckName::IdentifiantResolu,
            Outcome::Ok,
            "version trouvée dans le corpus",
        ),
        (Some(other), None) => check(
            CheckName::IdentifiantResolu,
            Outcome::Echec,
            format!(
                "le corpus a renvoyé {} au lieu de {}",
                other.official_id, claim.official_id
            ),
        ),
        (None, None) => check(
            CheckName::IdentifiantResolu,
            Outcome::Echec,
            "identifiant absent du corpus ingéré",
        ),
    });

    let resolution = if payload.sibling_versions.is_empty() {
        None
    } else {
        Some(resolve_at(
            &payload.sibling_versions,
            claim.as_of,
            payload.knowledge_date,
        ))
    };

    if let Some(candidate) = candidate {
        // 3. Existence du passage.
        checks.push(match find_passage(&candidate.text, &claim.quote) {
            PassageOutcome::Found(span) => {
                let detail = if span.occurrences > 1 {
                    format!("passage trouvé ({} occurrences)", span.occurrences)
                } else {
                    "passage trouvé".to_string()
                };
                quote_span = Some(span);
                check(CheckName::PassagePresent, Outcome::Ok, detail)
            }
            PassageOutcome::NotFound(detail) => {
                check(CheckName::PassagePresent, Outcome::Echec, detail)
            }
            PassageOutcome::TooShort(detail) => {
                uncertainties.push("citation trop courte pour une vérification probante".into());
                check(CheckName::PassagePresent, Outcome::Indetermine, detail)
            }
        });

        // 4. Applicabilité temporelle.
        let period = &candidate.period;
        let knowledge = payload
            .knowledge_date
            .map(|k| k.to_string())
            .unwrap_or_else(|| "non communiquée".into());
        let start = period
            .valid_from
            .map(|d| format!("du {d}"))
            .unwrap_or_else(|| "à compter d'une date non fixée par la source".into());
        let end = match (period.valid_to, period.end_undetermined) {
            (Some(d), _) => format!("au {d}"),
            (None, true) => "jusqu'à une date non fixée par la source".into(),
            (None, false) => "sans date de fin connue".into(),
        };
        checks.push(match period.in_force_at(claim.as_of, payload.knowledge_date) {
            InForce::Oui => check(
                CheckName::ApplicabiliteTemporelle,
                Outcome::Ok,
                format!("en vigueur le {} (période {} {})", claim.as_of, start, end),
            ),
            InForce::Indetermine => {
                uncertainties.push(if period.valid_from.is_none() {
                    "entrée en vigueur à une date non fixée par la source".into()
                } else {
                    "abrogation à une date non fixée par la source".into()
                });
                check(
                    CheckName::ApplicabiliteTemporelle,
                    Outcome::Indetermine,
                    format!(
                        "applicabilité au {} indéterminée (période {} {}) ; état connu jusqu'au {}, date de connaissance du corpus",
                        claim.as_of, start, end, knowledge
                    ),
                )
            }
            InForce::Non if !period.ever_in_force() => check(
                CheckName::ApplicabiliteTemporelle,
                Outcome::Echec,
                format!(
                    "version jamais entrée en vigueur (statut source {})",
                    period.status_raw
                ),
            ),
            InForce::Non => {
                let replacement = match &resolution {
                    Some(Resolution::Unique { official_id }) => {
                        format!(" ; version en vigueur à cette date : {official_id}")
                    }
                    Some(Resolution::Aucune) => {
                        " ; aucune version connue en vigueur à cette date".into()
                    }
                    Some(Resolution::Ambigue { official_ids }) => {
                        format!(" ; versions concurrentes : {}", official_ids.join(", "))
                    }
                    Some(Resolution::Indeterminee {
                        possibly_in_force, ..
                    }) => format!(
                        " ; versions d'applicabilité indéterminée : {}",
                        possibly_in_force.join(", ")
                    ),
                    None => String::new(),
                };
                check(
                    CheckName::ApplicabiliteTemporelle,
                    Outcome::Echec,
                    format!(
                        "non en vigueur le {} (période {} {}){}",
                        claim.as_of, start, end, replacement
                    ),
                )
            }
        });
        if period.valid_from.is_some_and(|start| start > claim.as_of)
            && period.status_raw.ends_with("_DIFF")
        {
            uncertainties.push("disposition à entrée en vigueur différée".into());
        }

        // 5. Territoire.
        checks.push(match (&claim.territory, &candidate.territorial_scope) {
            (None, _) => {
                uncertainties.push("territoire de la question non précisé".into());
                check(
                    CheckName::Territoire,
                    Outcome::Indetermine,
                    "territoire de la question non précisé",
                )
            }
            (Some(_), None) => {
                uncertainties.push("champ territorial non renseigné par la source".into());
                check(
                    CheckName::Territoire,
                    Outcome::Indetermine,
                    "la source ne renseigne pas le champ territorial de cette version",
                )
            }
            (Some(t), Some(scope)) if scope.iter().any(|s| s == t) => check(
                CheckName::Territoire,
                Outcome::Ok,
                format!("applicable au territoire {t}"),
            ),
            (Some(t), Some(scope)) => check(
                CheckName::Territoire,
                Outcome::Echec,
                format!(
                    "territoire {t} hors du champ déclaré ({})",
                    scope.join(", ")
                ),
            ),
        });
    }

    // Cohérence des données temporelles (chevauchements de versions).
    if let Some(Resolution::Ambigue { official_ids }) = &resolution {
        uncertainties.push("plusieurs versions en vigueur à la même date dans le corpus".into());
        checks.push(check(
            CheckName::CoherenceTemporelle,
            Outcome::Indetermine,
            format!("versions concurrentes : {}", official_ids.join(", ")),
        ));
    }

    // 6 et 7. Hors périmètre déterministe : explicitement non évalués.
    checks.push(check(
        CheckName::AdequationRaisonnement,
        Outcome::NonEvalue,
        "adéquation au raisonnement : contrôle par le vérificateur indépendant ou un professionnel requis",
    ));
    checks.push(check(
        CheckName::Contradictions,
        Outcome::NonEvalue,
        "recherche de sources contraires : non couverte par le moteur déterministe",
    ));

    let verdict = if checks.iter().any(|c| c.outcome == Outcome::Echec) {
        Verdict::NonConforme
    } else if checks.iter().any(|c| c.outcome == Outcome::Indetermine) {
        Verdict::Incertain
    } else {
        Verdict::Conforme
    };

    VerifyCitationResult {
        verdict,
        identifier_family: family,
        checks,
        quote_span,
        resolution_at_date: resolution,
        uncertainties,
    }
}
