// Fichier généré par scripts/gen-contracts.mjs — ne pas modifier à la main.
// Source : packages/contracts/schemas/*.schema.json (modèles Pydantic).

/**
 * Nature d'une affirmation : le système ne mélange jamais ces catégories.
 *
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "ClaimKind".
 */
export type ClaimKind = "FAIT" | "HYPOTHESE" | "DROIT_APPLICABLE" | "INTERPRETATION" | "RECOMMANDATION";
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "SupportStatus".
 */
export type SupportStatus = "FONDEE" | "INCERTAINE" | "BLOQUEE";
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "CheckOutcome".
 */
export type CheckOutcome = "OK" | "ECHEC" | "INDETERMINE" | "NON_EVALUE";
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "Verdict".
 */
export type Verdict = "CONFORME" | "INCERTAIN" | "NON_CONFORME";

export interface AvocatExpertContracts {
  SourcedAnswer?: SourcedAnswer;
  AnswerRequest?: AnswerRequest;
  CitationVerification?: CitationVerification;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "SourcedAnswer".
 */
export interface SourcedAnswer {
  as_of: string;
  disclaimer: string;
  /**
   * Ex. EXTRACTIF : aucune génération de texte par un modèle
   */
  mode: string;
  question_sha256: string;
  search: SearchResponse;
  statements: SourcedStatement[];
  status: SupportStatus;
  summary: string;
  uncertainties: string[];
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "SearchResponse".
 */
export interface SearchResponse {
  as_of: string;
  channels: ChannelStatus[];
  hits: SearchHit[];
  /**
   * Méthode de classement effectivement utilisée
   */
  ranking: string;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "ChannelStatus".
 */
export interface ChannelStatus {
  channel: string;
  detail: string;
  enabled: boolean;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "SearchHit".
 */
export interface SearchHit {
  /**
   * Extrait littéral du texte de la version
   */
  excerpt: string;
  /**
   * Canaux ayant produit le résultat : identifiant, lexical, sémantique
   */
  matched_by: string[];
  reference: SourceReference;
  score: number;
}
/**
 * Référence traçable vers une version précise d'une source officielle.
 *
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "SourceReference".
 */
export interface SourceReference {
  connector_version: string;
  /**
   * La source ne renseigne aucune date d'application : applicabilité indéterminée
   */
  dates_unknown?: boolean;
  document_official_id: string;
  document_title: string;
  /**
   * Fin (abrogation) annoncée par la source à une date non encore fixée
   */
  end_undetermined?: boolean;
  /**
   * Identifiant officiel de la version citée, ex. LEGIARTI…
   */
  official_id: string;
  /**
   * Numéro publié ; vide pour un article non numéroté
   */
  provision_number: string;
  /**
   * Nom (horodaté) de l'archive livrée par la source
   */
  source_archive: string;
  /**
   * Code de la source, ex. DILA_LEGI
   */
  source_code: string;
  source_file_sha256: string;
  source_path: string;
  /**
   * Statut brut publié par la source
   */
  source_status: string;
  /**
   * None : entrée en vigueur à une date non fixée par la source
   */
  valid_from: string | null;
  /**
   * None : pas de date de fin connue (voir end_undetermined)
   */
  valid_to: string | null;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "SourcedStatement".
 */
export interface SourcedStatement {
  citation: SourceReference | null;
  kind: ClaimKind;
  quote: string | null;
  support: SupportStatus;
  text: string;
  verification: CitationVerification | null;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "CitationVerification".
 */
export interface CitationVerification {
  checks: CitationCheck[];
  contract_version: string;
  engine_version: string;
  official_id: string;
  quote_end?: number | null;
  quote_start?: number | null;
  uncertainties: string[];
  verdict: Verdict;
  version_in_force_at_date?: string | null;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "CitationCheck".
 */
export interface CitationCheck {
  check: string;
  detail: string;
  outcome: CheckOutcome;
}
/**
 * This interface was referenced by `AvocatExpertContracts`'s JSON-Schema
 * via the `definition` "AnswerRequest".
 */
export interface AnswerRequest {
  as_of?: string | null;
  max_sources?: number;
  question: string;
  territory?: string | null;
}
