//! Moteur déterministe de vérification des citations juridiques.
//!
//! Ce crate ne fait aucun appel réseau et aucune inférence statistique :
//! il applique des règles explicites (identifiant, présence du passage,
//! applicabilité temporelle, territoire) sur des données fournies par
//! l'appelant. Les contrôles non déterministes (adéquation au raisonnement,
//! contradictions doctrinales) sont explicitement signalés comme
//! `NonEvalue` et ne sont jamais présentés comme réussis.

pub mod contract;
pub mod identifiers;
pub mod normalize;
pub mod temporal;
pub mod verify;

pub use contract::{Request, Response, CONTRACT_VERSION};
pub use verify::handle;
