//! Reconnaissance syntaxique des identifiants officiels.
//!
//! Seules les familles effectivement observées dans les sources ingérées
//! (dumps LEGI de la DILA) et l'ECLI sont reconnues. Toute autre famille est
//! rejetée tant qu'un connecteur vérifié ne l'a pas introduite.

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum IdentifierFamily {
    /// Version d'article LEGI (`LEGIARTI` + 12 chiffres).
    LegiArticle,
    /// Texte LEGI (`LEGITEXT` + 12 chiffres).
    LegiText,
    /// Section LEGI (`LEGISCTA` + 12 chiffres).
    LegiSection,
    /// Texte JORF (`JORFTEXT` + 12 chiffres).
    JorfText,
    /// Article JORF (`JORFARTI` + 12 chiffres).
    JorfArticle,
    /// European Case Law Identifier.
    Ecli,
}

fn patterns() -> &'static [(IdentifierFamily, Regex)] {
    static PATTERNS: OnceLock<Vec<(IdentifierFamily, Regex)>> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        let raw: [(IdentifierFamily, &str); 6] = [
            (IdentifierFamily::LegiArticle, r"^LEGIARTI\d{12}$"),
            (IdentifierFamily::LegiText, r"^LEGITEXT\d{12}$"),
            (IdentifierFamily::LegiSection, r"^LEGISCTA\d{12}$"),
            (IdentifierFamily::JorfText, r"^JORFTEXT\d{12}$"),
            (IdentifierFamily::JorfArticle, r"^JORFARTI\d{12}$"),
            (
                IdentifierFamily::Ecli,
                r"^ECLI:[A-Z]{2}:[A-Z0-9]{1,7}:\d{4}:[A-Za-z0-9.]{1,25}$",
            ),
        ];
        raw.into_iter()
            .filter_map(|(family, pattern)| Regex::new(pattern).ok().map(|re| (family, re)))
            .collect()
    })
}

/// Retourne la famille d'un identifiant officiel, ou `None` s'il n'est pas reconnu.
pub fn classify(identifier: &str) -> Option<IdentifierFamily> {
    patterns()
        .iter()
        .find(|(_, re)| re.is_match(identifier))
        .map(|(family, _)| *family)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognises_legi_and_jorf_identifiers() {
        assert_eq!(
            classify("LEGIARTI000051831141"),
            Some(IdentifierFamily::LegiArticle)
        );
        assert_eq!(
            classify("LEGITEXT000023983208"),
            Some(IdentifierFamily::LegiText)
        );
        assert_eq!(
            classify("JORFTEXT000031738398"),
            Some(IdentifierFamily::JorfText)
        );
    }

    #[test]
    fn rejects_malformed_identifiers() {
        assert_eq!(classify("LEGIARTI00005183114"), None);
        assert_eq!(classify("LEGIARTI0000518311410"), None);
        assert_eq!(classify("legiarti000051831141"), None);
        assert_eq!(classify(" LEGIARTI000051831141"), None);
        assert_eq!(classify("Code civil art. 1240"), None);
    }

    #[test]
    fn recognises_ecli_shape() {
        assert_eq!(
            classify("ECLI:FR:CCASS:2023:C100123"),
            Some(IdentifierFamily::Ecli)
        );
        assert_eq!(classify("ECLI:FR"), None);
    }
}
