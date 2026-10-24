//! Résolution temporelle des versions d'une disposition.
//!
//! Convention : la période de validité juridique est l'intervalle semi-ouvert
//! `[valid_from, valid_to)`. `valid_to = None` signifie « sans date de fin
//! connue ». Une version dont `valid_to <= valid_from` n'a jamais été en
//! vigueur (cas des versions « mort-nées » observées dans LEGI).

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VersionPeriod {
    pub official_id: String,
    pub valid_from: NaiveDate,
    pub valid_to: Option<NaiveDate>,
    /// Statut brut fourni par la source (ex. `VIGUEUR`, `MODIFIE_MORT_NE`).
    pub status_raw: String,
}

impl VersionPeriod {
    pub fn ever_in_force(&self) -> bool {
        self.valid_to.is_none_or(|end| end > self.valid_from)
    }

    pub fn in_force_at(&self, date: NaiveDate) -> bool {
        self.ever_in_force()
            && self.valid_from <= date
            && self.valid_to.is_none_or(|end| date < end)
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
}

pub fn resolve_at(versions: &[VersionPeriod], date: NaiveDate) -> Resolution {
    let mut matching: Vec<String> = versions
        .iter()
        .filter(|v| v.in_force_at(date))
        .map(|v| v.official_id.clone())
        .collect();
    matching.sort();
    matching.dedup();
    match matching.len() {
        0 => Resolution::Aucune,
        1 => Resolution::Unique {
            official_id: matching.remove(0),
        },
        _ => Resolution::Ambigue {
            official_ids: matching,
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
            valid_from: d(from),
            valid_to: to.map(d),
            status_raw: status.into(),
        }
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
            resolve_at(&versions, d("2023-10-09")),
            Resolution::Unique {
                official_id: "LEGIARTI000046886100".into()
            }
        );
        // Le 2023-10-10, la version vide et la version mort-née sont exclues.
        assert_eq!(
            resolve_at(&versions, d("2023-10-10")),
            Resolution::Unique {
                official_id: "LEGIARTI000048173002".into()
            }
        );
    }

    #[test]
    fn gap_in_corpus_yields_none() {
        // Versions 2024-02-14 → 2025-07-01 absentes de cet extrait.
        assert_eq!(resolve_at(&d251_1(), d("2024-06-01")), Resolution::Aucune);
    }

    #[test]
    fn open_ended_version() {
        assert_eq!(
            resolve_at(&d251_1(), d("2026-10-24")),
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
            resolve_at(&versions, d("2022-01-01")),
            Resolution::Ambigue { .. }
        ));
    }

    #[test]
    fn stillborn_version_never_in_force() {
        let mort_ne = v("X", "2021-01-01", Some("2020-12-08"), "MODIFIE_MORT_NE");
        assert!(!mort_ne.ever_in_force());
        assert!(!mort_ne.in_force_at(d("2021-01-01")));
    }
}
