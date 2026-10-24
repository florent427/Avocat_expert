//! Résolution temporelle des versions d'une disposition.
//!
//! Convention : la période de validité juridique est l'intervalle semi-ouvert
//! `[valid_from, valid_to)`. `valid_to = None` signifie « sans date de fin
//! connue ». Une version dont `valid_to <= valid_from` n'a jamais été en
//! vigueur (cas des versions « mort-nées » observées dans LEGI).
//!
//! Dates non fixées par la source (LEGI : sentinelle 2222-02-22) :
//! `valid_from = None` (entrée en vigueur non fixée) ou `end_undetermined`
//! (abrogation à une date non fixée). L'état de ces versions n'est connu que
//! jusqu'à la date de connaissance du corpus (dernière livraison intégrée) ;
//! au-delà, il est indéterminé. Sans date de connaissance, il est toujours
//! indéterminé. Une version sans aucune date d'application renseignée
//! (`dates_unknown`) est indéterminée à toute date antérieure à sa fin.

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VersionPeriod {
    pub official_id: String,
    /// `None` : entrée en vigueur à une date non fixée par la source.
    pub valid_from: Option<NaiveDate>,
    pub valid_to: Option<NaiveDate>,
    /// Fin (abrogation) à une date non fixée par la source.
    #[serde(default)]
    pub end_undetermined: bool,
    /// Aucune date d'application renseignée par la source.
    #[serde(default)]
    pub dates_unknown: bool,
    /// Statut brut fourni par la source (ex. `VIGUEUR`, `MODIFIE_MORT_NE`).
    pub status_raw: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum InForce {
    Oui,
    Non,
    Indetermine,
}

impl VersionPeriod {
    pub fn ever_in_force(&self) -> bool {
        match (self.valid_from, self.valid_to) {
            (Some(start), Some(end)) => end > start,
            _ => true,
        }
    }

    pub fn in_force_at(&self, date: NaiveDate, knowledge_date: Option<NaiveDate>) -> InForce {
        let known = knowledge_date.is_some_and(|k| date <= k);
        if self.valid_to.is_some_and(|end| date >= end) {
            return InForce::Non;
        }
        if self.dates_unknown {
            return InForce::Indetermine;
        }
        let Some(start) = self.valid_from else {
            return if known {
                InForce::Non
            } else {
                InForce::Indetermine
            };
        };
        if !self.ever_in_force() || date < start {
            return InForce::Non;
        }
        if self.end_undetermined && !known {
            return InForce::Indetermine;
        }
        InForce::Oui
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Resolution {
    /// Exactement une version en vigueur à la date.
    Unique { official_id: String },
    /// Aucune version en vigueur à la date.
    Aucune,
    /// Plusieurs versions se chevauchent : anomalie de données à signaler.
    Ambigue { official_ids: Vec<String> },
    /// Au moins une version a une applicabilité indéterminée à la date (date
    /// non fixée par la source) : aucune version ne peut être désignée avec
    /// certitude.
    Indeterminee {
        in_force: Vec<String>,
        possibly_in_force: Vec<String>,
    },
}

pub fn resolve_at(
    versions: &[VersionPeriod],
    date: NaiveDate,
    knowledge_date: Option<NaiveDate>,
) -> Resolution {
    let collect = |state: InForce| {
        let mut ids: Vec<String> = versions
            .iter()
            .filter(|v| v.in_force_at(date, knowledge_date) == state)
            .map(|v| v.official_id.clone())
            .collect();
        ids.sort();
        ids.dedup();
        ids
    };
    let mut in_force = collect(InForce::Oui);
    let possibly_in_force = collect(InForce::Indetermine);
    if !possibly_in_force.is_empty() {
        return Resolution::Indeterminee {
            in_force,
            possibly_in_force,
        };
    }
    match in_force.len() {
        0 => Resolution::Aucune,
        1 => Resolution::Unique {
            official_id: in_force.remove(0),
        },
        _ => Resolution::Ambigue {
            official_ids: in_force,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(s: &str) -> NaiveDate {
        NaiveDate::parse_from_str(s, "%Y-%m-%d").unwrap_or_default()
    }

    fn v(id: &str, from: &str, to: Option<&str>, status: &str) -> VersionPeriod {
        VersionPeriod {
            official_id: id.into(),
            valid_from: Some(d(from)),
            valid_to: to.map(d),
            end_undetermined: false,
            dates_unknown: false,
            status_raw: status.into(),
        }
    }

    const KNOWLEDGE: &str = "2026-10-23";

    fn at(versions: &[VersionPeriod], date: &str) -> Resolution {
        resolve_at(versions, d(date), Some(d(KNOWLEDGE)))
    }

    /// Extrait réel de la chaîne de versions de l'article D251-1 du code de
    /// l'énergie (dump LEGI DILA du 2026-10-23).
    fn d251_1() -> Vec<VersionPeriod> {
        vec![
            v(
                "LEGIARTI000046886100",
                "2023-01-01",
                Some("2023-10-10"),
                "MODIFIE",
            ),
            v(
                "LEGIARTI000048090098",
                "2023-10-10",
                Some("2023-10-10"),
                "MODIFIE",
            ),
            v(
                "LEGIARTI000048170646",
                "2023-10-10",
                Some("2023-10-09"),
                "MODIFIE_MORT_NE",
            ),
            v(
                "LEGIARTI000048173002",
                "2023-10-10",
                Some("2024-02-14"),
                "MODIFIE",
            ),
            v("LEGIARTI000051831141", "2025-07-01", None, "VIGUEUR"),
        ]
    }

    #[test]
    fn half_open_interval_boundaries() {
        let versions = d251_1();
        assert_eq!(
            at(&versions, "2023-10-09"),
            Resolution::Unique {
                official_id: "LEGIARTI000046886100".into()
            }
        );
        // Le 2023-10-10, la version vide et la version mort-née sont exclues.
        assert_eq!(
            at(&versions, "2023-10-10"),
            Resolution::Unique {
                official_id: "LEGIARTI000048173002".into()
            }
        );
    }

    #[test]
    fn gap_in_corpus_yields_none() {
        // Versions 2024-02-14 → 2025-07-01 absentes de cet extrait.
        assert_eq!(at(&d251_1(), "2024-06-01"), Resolution::Aucune);
    }

    #[test]
    fn open_ended_version() {
        assert_eq!(
            at(&d251_1(), "2026-10-24"),
            Resolution::Unique {
                official_id: "LEGIARTI000051831141".into()
            }
        );
    }

    #[test]
    fn overlapping_versions_are_ambiguous() {
        let versions = vec![
            v("A", "2020-01-01", None, "VIGUEUR"),
            v("B", "2021-01-01", None, "VIGUEUR"),
        ];
        assert!(matches!(
            at(&versions, "2022-01-01"),
            Resolution::Ambigue { .. }
        ));
    }

    #[test]
    fn stillborn_version_never_in_force() {
        let mort_ne = v("X", "2021-01-01", Some("2020-12-08"), "MODIFIE_MORT_NE");
        assert!(!mort_ne.ever_in_force());
        assert_eq!(
            mort_ne.in_force_at(d("2021-01-01"), Some(d(KNOWLEDGE))),
            InForce::Non
        );
    }

    /// Article 289 du CGI (LEGIARTI000048827413, livraison du 2026-10-23) :
    /// ABROGE_DIFF, DATE_FIN 2222-02-22 (abrogation non fixée).
    fn abrogation_non_fixee() -> VersionPeriod {
        VersionPeriod {
            official_id: "LEGIARTI000048827413".into(),
            valid_from: Some(d("2023-12-31")),
            valid_to: None,
            end_undetermined: true,
            dates_unknown: false,
            status_raw: "ABROGE_DIFF".into(),
        }
    }

    #[test]
    fn undetermined_end_is_known_only_until_knowledge_date() {
        let versions = vec![abrogation_non_fixee()];
        assert_eq!(
            at(&versions, "2026-10-23"),
            Resolution::Unique {
                official_id: "LEGIARTI000048827413".into()
            }
        );
        assert_eq!(
            at(&versions, "2030-01-01"),
            Resolution::Indeterminee {
                in_force: vec![],
                possibly_in_force: vec!["LEGIARTI000048827413".into()]
            }
        );
        // Sans date de connaissance, aucune certitude possible.
        assert_eq!(
            abrogation_non_fixee().in_force_at(d("2024-06-01"), None),
            InForce::Indetermine
        );
        // Avant le début, la version n'est pas en vigueur, quelle que soit la connaissance.
        assert_eq!(
            abrogation_non_fixee().in_force_at(d("2020-01-01"), None),
            InForce::Non
        );
    }

    #[test]
    fn undetermined_start_is_not_in_force_at_known_dates() {
        let pending = VersionPeriod {
            official_id: "B".into(),
            valid_from: None,
            valid_to: None,
            end_undetermined: false,
            dates_unknown: false,
            status_raw: "VIGUEUR_DIFF".into(),
        };
        let current = v("A", "2020-01-01", None, "VIGUEUR");
        let versions = vec![current, pending];
        assert_eq!(
            at(&versions, "2026-01-01"),
            Resolution::Unique {
                official_id: "A".into()
            }
        );
        assert_eq!(
            at(&versions, "2027-06-01"),
            Resolution::Indeterminee {
                in_force: vec!["A".into()],
                possibly_in_force: vec!["B".into()]
            }
        );
    }

    #[test]
    fn unknown_dates_are_always_indeterminate() {
        // Stock du 2025-07-13 : LEGIARTI000006850356, ETAT vide, dates 2999-01-01.
        let unknown = VersionPeriod {
            official_id: "LEGIARTI000006850356".into(),
            valid_from: None,
            valid_to: None,
            end_undetermined: false,
            dates_unknown: true,
            status_raw: String::new(),
        };
        for date in ["1990-01-01", "2026-10-23", "2030-01-01"] {
            assert_eq!(
                unknown.in_force_at(d(date), Some(d(KNOWLEDGE))),
                InForce::Indetermine
            );
        }
    }
}
