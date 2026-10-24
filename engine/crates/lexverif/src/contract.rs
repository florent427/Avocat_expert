//! Contrat d'échange JSON (stdin/stdout) du moteur `lexverif`.
//!
//! Le contrat est versionné par `CONTRACT_VERSION`. Toute évolution
//! incompatible incrémente la version ; les champs inconnus sont refusés.

use crate::identifiers::IdentifierFamily;
use crate::temporal::{Resolution, VersionPeriod};
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

pub const CONTRACT_VERSION: &str = "1";

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub contract_version: String,
    #[serde(flatten)]
    pub command: Command,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "command", content = "payload", rename_all = "snake_case")]
pub enum Command {
    VerifyCitation(VerifyCitationPayload),
    ResolveAt(ResolveAtPayload),
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerifyCitationPayload {
    pub citation: CitationClaim,
    /// Version résolue par le dépôt à partir de l'identifiant cité ; `None`
    /// si l'identifiant est introuvable dans le corpus.
    pub candidate: Option<CandidateVersion>,
    /// Toutes les versions connues de la même disposition (y compris `candidate`).
    #[serde(default)]
    pub sibling_versions: Vec<VersionPeriod>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CitationClaim {
    pub official_id: String,
    pub quote: String,
    /// Date à laquelle le droit est apprécié.
    pub as_of: NaiveDate,
    /// Territoire visé (code libre, ex. `FR`, `FR-976`), si connu.
    pub territory: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateVersion {
    pub official_id: String,
    pub text: String,
    pub period: VersionPeriod,
    /// Territoires d'application déclarés par la source ; `None` si la
    /// source ne renseigne pas cette information.
    pub territorial_scope: Option<Vec<String>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResolveAtPayload {
    pub as_of: NaiveDate,
    pub versions: Vec<VersionPeriod>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CheckName {
    SourceIdentifiee,
    IdentifiantResolu,
    PassagePresent,
    ApplicabiliteTemporelle,
    Territoire,
    CoherenceTemporelle,
    AdequationRaisonnement,
    Contradictions,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Outcome {
    Ok,
    Echec,
    Indetermine,
    /// Contrôle hors du périmètre déterministe : il reste à effectuer.
    NonEvalue,
}

#[derive(Debug, Clone, Serialize)]
pub struct Check {
    pub check: CheckName,
    pub outcome: Outcome,
    pub detail: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Verdict {
    /// Tous les contrôles déterministes sont réussis.
    Conforme,
    /// Aucun échec, mais au moins un contrôle déterministe est indéterminé.
    Incertain,
    /// Au moins un contrôle déterministe a échoué : la citation doit être bloquée.
    NonConforme,
}

#[derive(Debug, Clone, Serialize)]
pub struct QuoteSpan {
    pub start: usize,
    pub end: usize,
    pub occurrences: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct VerifyCitationResult {
    pub verdict: Verdict,
    pub identifier_family: Option<IdentifierFamily>,
    pub checks: Vec<Check>,
    /// Position (octets UTF-8) du premier segment cité dans le texte de la version.
    pub quote_span: Option<QuoteSpan>,
    pub resolution_at_date: Option<Resolution>,
    pub uncertainties: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum Response {
    Ok {
        contract_version: &'static str,
        engine_version: &'static str,
        result: ResultBody,
    },
    Error {
        contract_version: &'static str,
        engine_version: &'static str,
        error: String,
    },
}

#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum ResultBody {
    VerifyCitation(VerifyCitationResult),
    ResolveAt(Resolution),
}
